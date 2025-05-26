# lambda_function.py
"""
Lambda 함수 진입점 모듈
AWS Lambda 함수 핸들러를 정의합니다.
"""
import json
import logging
import traceback
from slack_bolt import App
from slack_bolt.adapter.aws_lambda import SlackRequestHandler

# 내부 모듈 임포트
from config import Config
import aws_clients
from aws_clients import initialize_aws_clients
from response_parser import ResponseParser
from slack_action_handlers import SlackActionHandler
from slack_event_handlers import register_event_handlers

# 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(funcName)s - %(message)s')
for handler in logger.handlers:
    handler.setFormatter(formatter)

# 초기화 함수
def initialize_app():
    """
    슬랙 앱 및 관련 구성요소 초기화
    
    Returns:
        tuple: (app, handler, bot_id)
    """
    # 설정 유효성 검증
    if not Config.validate():
        logger.error("필수 설정이 누락되었습니다.")
        raise ValueError("Required configuration is missing")
        
    # AWS 클라이언트 초기화 (한 번만)
    logger.info("Initializing AWS clients...")
    initialize_aws_clients()
    
    # 초기화 결과 확인
    if aws_clients.bedrock_agent_runtime is None:
        logger.error("bedrock_agent_runtime initialization failed!")
    else:
        logger.info("bedrock_agent_runtime successfully initialized")
    
    # Slack 앱 초기화
    try:
        logger.info("Initializing Slack app")
        app = App(
            token=Config.SLACK_BOT_TOKEN,
            signing_secret=Config.SLACK_SIGNING_SECRET,
            process_before_response=True,
        )
        logger.info("Slack app initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing Slack app: {e}", exc_info=True)
        raise
    
    # 의존성 초기화
    response_parser = ResponseParser()
    response_parser.set_slack_client(app.client)
    
    # 액션 핸들러 등록
    action_handler = SlackActionHandler(app, response_parser)
    
    # 슬랙 봇 ID 가져오기
    bot_id = None
    try:
        logger.info("Getting bot info from Slack API")
        bot_info = app.client.auth_test()
        bot_id = bot_info["user_id"]
        logger.info(f"Bot ID retrieved successfully: {bot_id}")
    except Exception as e:
        logger.error(f"Error getting bot ID: {e}", exc_info=True)
        logger.warning("Bot ID retrieval failed, mention parsing may not work correctly")
    
    # 이벤트 핸들러 등록
    register_event_handlers(app, bot_id)
    
    # Lambda 핸들러 초기화
    try:
        logger.info("Initializing SlackRequestHandler")
        handler = SlackRequestHandler(app)
        logger.info("SlackRequestHandler initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing SlackRequestHandler: {e}", exc_info=True)
        raise
    
    return app, handler, bot_id

# 전역 변수로 초기화
try:
    app, handler, bot_id = initialize_app()
    initialization_failed = False
    logger.info("Application initialization completed successfully")
except Exception as e:
    logger.error(f"Initialization failed: {e}", exc_info=True)
    # Lambda 컨테이너는 재사용될 수 있으므로 전역 에러 상태 표시
    initialization_failed = True

def lambda_handler(event, context):
    """
    Lambda 함수 핸들러 - Slack 이벤트 처리
    
    Args:
        event (dict): Lambda 이벤트 데이터
        context: Lambda 컨텍스트 객체
        
    Returns:
        dict: HTTP 응답
    """
    logger.info(f"Lambda 함수 호출됨: {json.dumps(event)[:500]}...")
    
    # 초기화 실패 시 오류 응답
    if initialization_failed:
        logger.error("Unable to process request due to initialization failure")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Service initialization failed"})
        }
    
    # AWS 클라이언트 상태 로깅 (재초기화하지 않음)
    if aws_clients.bedrock_agent_runtime is None:
        logger.warning("bedrock_agent_runtime is None in lambda_handler - using fallback mode")
    else:
        logger.debug("bedrock_agent_runtime is available in lambda_handler")

    try:
        # 1. 중복 이벤트 확인 (헤더에서 x-slack-retry-num 체크)
        headers = event.get("headers", {})
        if headers and "x-slack-retry-num" in headers:
            retry_num = headers["x-slack-retry-num"]
            logger.info(f"Slack 재시도 감지: x-slack-retry-num={retry_num}")
            # 재시도 이벤트는 바로 200 응답 반환 (이미 처리 중이므로)
            return {
                "statusCode": 200,
                "body": json.dumps({"status": "ok"})
            }

        # 2. URL 검증 요청 처리 (challenge)
        if "body" in event:
            try:
                body_json = json.loads(event["body"])
                if "challenge" in body_json:
                    logger.info("URL 검증 요청 처리")
                    return {
                        "statusCode": 200,
                        "body": json.dumps({"challenge": body_json["challenge"]})
                    }
            except:
                # JSON 파싱 실패해도 계속 진행
                pass
        
        # 3. Slack 이벤트 처리를 Bolt 핸들러에 위임
        result = handler.handle(event, context)
        
        # 4. 핸들러가 정상적으로 처리하지 못한 경우 기본 응답 반환
        if not result:
            return {
                "statusCode": 200,
                "body": json.dumps({"status": "ok"})
            }
        
        # 5. 핸들러의 응답 반환
        return result
    
    except Exception as e:
        logger.error(f"Lambda 핸들러 처리 중 오류 발생: {e}", exc_info=True)
        logger.error(f"Full stack trace: {traceback.format_exc()}")
        
        # 6. 오류가 발생해도 Slack에는 성공 응답 (이벤트는 수신했음을 알림)
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "ok", "error": str(e)[:100]})
        }