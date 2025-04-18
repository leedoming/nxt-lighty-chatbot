# slackbot_core.py에서 선언된 코드 임포트
from slackbot_core import (
    app, Config, bot_id, logger, DynamoDBManager, SlackManager, BedrockManager, 
    is_duplicate_event, MSG_PREVIOUS, MSG_RESPONSE, MSG_ERROR, handler
)
import json
import re
import traceback
from typing import Optional, List


def conversation(say, query: str, thread_ts: Optional[str] = None,
               channel: Optional[str] = None, client_msg_id: Optional[str] = None,
               user: Optional[str] = None) -> None:
    """Main conversation handler that processes queries and returns responses"""
    logger.info(f"Starting conversation handler - query: {query}, channel: {channel}, thread_ts: {thread_ts}")

    try:
        # 초기 메시지 전송 (Step 1)
        logger.info("Step 1: Sending initial status message")
        try:
            result = say(text=Config.BOT_CURSOR, thread_ts=thread_ts)
            latest_ts = result["ts"]
            logger.info(f"Initial message sent successfully, ts: {latest_ts}")
        except Exception as e:
            logger.error(f"Error sending initial message: {e}", exc_info=True)
            logger.error(f"Error details - channel: {channel}, thread_ts: {thread_ts}")
            logger.error(f"Full stack trace: {traceback.format_exc()}")
            return  # 중요: 초기 메시지 실패 시 빠른 종료

        # 스레드 히스토리 조회 (Step 2)
        thread_history = []
        if thread_ts:
            logger.info("Step 2: Getting thread history")
            try:
                # 이전 메시지 확인 중 상태 업데이트
                logger.info("Updating with 'getting previous messages' status")
                SlackManager.update_message(say, channel, thread_ts, latest_ts, MSG_PREVIOUS)
                
                # 스레드 히스토리 조회
                thread_history = SlackManager.get_thread_history(channel, thread_ts, client_msg_id)
                logger.info(f"Thread history retrieved, {len(thread_history)} messages")
            except Exception as e:
                logger.error(f"Error getting thread history: {e}", exc_info=True)
                # 히스토리 실패는 치명적이지 않음 - 계속 진행
        else:
            logger.info("Step 2: No thread_ts, skipping thread history")

        # 응답 생성 중 상태 업데이트 (Step 3)
        logger.info("Step 3: Updating with 'processing' status")
        try:
            SlackManager.update_message(say, channel, thread_ts, latest_ts, MSG_RESPONSE)
            logger.info("Processing status updated successfully")
        except Exception as e:
            logger.error(f"Error updating processing status: {e}", exc_info=True)
            # 계속 진행 시도
        
        # 프롬프트 생성 및 Bedrock 응답 가져오기 (Step 4)
        logger.info("Step 4: Creating prompt and getting Bedrock response")
        prompt = BedrockManager.create_prompt(query, thread_history)
        message = BedrockManager.invoke_model(prompt)
        logger.info(f"Response message generated: {len(message)} characters")

        # 메시지 데이터베이스에 저장 (선택적)
        if user and Config.USE_DYNAMODB:
            logger.info(f"Storing conversation in DynamoDB for user: {user}")
            try:
                DynamoDBManager.put_context(thread_ts, user, f"query: {query}, response: {message[:100]}...")
            except Exception as e:
                logger.error(f"Error storing conversation in DynamoDB: {e}", exc_info=True)
                # DB 저장 실패는 비치명적 - 계속 진행

        # 최종 응답 전송 (Step 5)
        logger.info("Step 5: Sending final response")
        try:
            final_message, final_ts = SlackManager.update_message(say, channel, thread_ts, latest_ts, message)
            logger.info(f"Final response sent successfully, ts: {final_ts}")
        except Exception as e:
            logger.error(f"Error sending final response: {e}", exc_info=True)
            # 마지막 시도 - 직접 메시지 보내기
            try:
                say(text="응답을 보내는 중 오류가 발생했습니다. 관리자에게 문의하세요.", thread_ts=thread_ts)
            except:
                pass  # 정말 최후의 시도도 실패하면 포기

    except Exception as e:
        logger.error(f"Error in conversation handler: {e}", exc_info=True)
        logger.error(f"Full stack trace: {traceback.format_exc()}")
        # Update with error message if possible
        try:
            if 'latest_ts' in locals():
                logger.info("Attempting to send error message to user")
                SlackManager.update_message(say, channel, thread_ts, latest_ts, MSG_ERROR)
                logger.info("Error message sent to user successfully")
        except Exception as inner_e:
            logger.error(f"Failed to send error message: {inner_e}", exc_info=True)


# Bolt 프레임워크 핸들러 정의
@app.event("app_mention")
def handle_app_mention_events(body, say, logger):
    """Handle mentions of the bot in channels"""
    logger.info(f"Received app_mention event: {json.dumps(body)[:500]}...")

    # 중복 이벤트 확인 (중요: 최우선으로 확인)
    if is_duplicate_event(body):
        logger.info("중복된, 이미 처리된 멘션 이벤트이므로 무시합니다.")
        return
    
    try:
        event = body["event"]
        thread_ts = event.get("thread_ts", event.get("ts"))
        channel = event.get("channel")
        client_msg_id = event.get("client_msg_id")
        user = event.get("user")
        
        logger.info(f"멘션 이벤트 세부사항 - 채널: {channel}, 스레드: {thread_ts}, 사용자: {user}")

        # Check if the channel is allowed
        if Config.ALLOWED_CHANNEL_IDS != "None":
            logger.info(f"Checking if channel {channel} is in allowed channels: {Config.ALLOWED_CHANNEL_IDS}")
            allowed_channel_ids = Config.ALLOWED_CHANNEL_IDS.split(",")
            if channel not in allowed_channel_ids:
                first_channel = f"<#{allowed_channel_ids[0]}>"
                message = Config.ALLOWED_CHANNEL_MESSAGE.format(first_channel)
                logger.info(f"Channel {channel} not allowed, sending message: {message}")
                say(text=message, thread_ts=thread_ts)
                return

        # Extract query text (remove the bot mention)
        if bot_id:
            prompt = re.sub(f"<@{bot_id}>", "", event["text"]).strip()
        else:
            # Bot ID를 구하지 못한 경우 전체 텍스트 사용
            prompt = event["text"].strip()
        logger.info(f"Extracted prompt: '{prompt}'")
        
        # Process the conversation
        conversation(say, prompt, thread_ts, channel, client_msg_id, user)
    except Exception as e:
        logger.error(f"Error in handle_mention: {e}", exc_info=True)
        logger.error(f"Full stack trace: {traceback.format_exc()}")
        
        # 마지막 시도 - 직접 에러 메시지 보내기
        try:
            if 'channel' in locals() and 'thread_ts' in locals():
                say(text=f"오류가 발생했습니다. 관리자에게 문의하세요. 오류 정보: {str(e)[:100]}", thread_ts=thread_ts)
        except:
            pass  # 정말 최후의 시도도 실패하면 포기


@app.event("message")
def handle_message(body, say, logger):
    """Handle direct messages to the bot"""
    logger.info(f"Received message event: {json.dumps(body)[:500]}...")

    # 중복 이벤트 확인 (중요: 최우선으로 확인)
    if is_duplicate_event(body):
        logger.info("중복된, 이미 처리된 메시지 이벤트이므로 무시합니다.")
        return

    try:
        event = body["event"]

        # Ignore messages from bots (including this bot)
        if event.get("bot_id"):
            logger.info("Ignoring message from bot")
            return

        # DM 채널에서만 응답 (channel 타입이 'im'인 경우)
        if "channel_type" not in event or event["channel_type"] != "im":
            logger.info(f"Ignoring message in non-DM channel type: {event.get('channel_type')}")
            return

        channel = event["channel"]
        client_msg_id = event.get("client_msg_id")
        user = event.get("user")
        prompt = event["text"].strip()
        logger.info(f"Processing DM: '{prompt}'")

        # Process the conversation (thread_ts=None for DMs)
        conversation(say, prompt, None, channel, client_msg_id, user)
        
    except Exception as e:
        logger.error(f"Error in handle_message: {e}", exc_info=True)
        logger.error(f"Full stack trace: {traceback.format_exc()}")
        
        # 마지막 시도 - 직접 에러 메시지 보내기
        try:
            if 'channel' in locals():
                say(text=f"DM 처리 중 오류가 발생했습니다. 관리자에게 문의하세요. 오류 정보: {str(e)[:100]}")
        except:
            pass  # 정말 최후의 시도도 실패하면 포기


def lambda_handler(event, context):
    """AWS Lambda 핸들러 함수"""
    logger.info(f"Lambda 함수 호출됨: {json.dumps(event)[:500]}...")
    
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
        
        # 3. 설정 유효성 검증
        if not Config.validate():
            logger.error("필수 설정이 누락되었습니다. Lambda 함수 종료합니다.")
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "서버 설정 오류가 발생했습니다."})
            }
        
        # 4. Slack 이벤트 처리를 Bolt 핸들러에 위임
        result = handler.handle(event, context)
        
        # 5. 핸들러가 정상적으로 처리하지 못한 경우 기본 응답 반환
        if not result:
            return {
                "statusCode": 200,
                "body": json.dumps({"status": "ok"})
            }
        
        # 6. 핸들러의 응답 반환
        return result
    
    except Exception as e:
        logger.error(f"Lambda 핸들러 처리 중 오류 발생: {e}", exc_info=True)
        logger.error(f"Full stack trace: {traceback.format_exc()}")
        
        # 7. 오류가 발생해도 Slack에는 성공 응답 (이벤트는 수신했음을 알림)
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "ok", "error": str(e)[:100]})
        }
