import boto3
import json
import os
import re
import time
import logging
import traceback
from datetime import datetime
from typing import List, Optional, Dict, Any

from slack_bolt import App, Say
from slack_bolt.adapter.aws_lambda import SlackRequestHandler
from slack_sdk.web import WebClient

from boto3.dynamodb.conditions import Key

# 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(funcName)s - %(message)s')
for handler in logger.handlers:
    handler.setFormatter(formatter)

# Environment configuration
class Config:
    """Configuration settings loaded from environment variables"""
    AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
    SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
    SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
    DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "")
    ALLOWED_CHANNEL_IDS = os.environ.get("ALLOWED_CHANNEL_IDS", "None")
    ALLOWED_CHANNEL_MESSAGE = os.environ.get(
        "ALLOWED_CHANNEL_MESSAGE", "Sorry, I'm not allowed to respond in this channel."
    )
    PERSONAL_MESSAGE = os.environ.get(
        "PERSONAL_MESSAGE", "You are a friendly and professional AI assistant."
    )
    SYSTEM_MESSAGE = os.environ.get("SYSTEM_MESSAGE", "None")
    MAX_LEN_SLACK = int(os.environ.get("MAX_LEN_SLACK", "2000"))
    MAX_LEN_BEDROCK = int(os.environ.get("MAX_LEN_BEDROCK", "4000"))
    MAX_THROTTLE_COUNT = int(os.environ.get("MAX_THROTTLE_COUNT", "100"))
    BOT_CURSOR = os.environ.get("BOT_CURSOR", ":robot_face:")
    BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    
    # 디버깅을 위해 DynamoDB 사용 여부를 제어하는 플래그
    USE_DYNAMODB = os.environ.get("USE_DYNAMODB", "true").lower() == "true"
    USE_BEDROCK = os.environ.get("USE_BEDROCK", "true").lower() == "true"
    # 테스트용 응답
    TEST_RESPONSE = os.environ.get("TEST_RESPONSE", "안녕하세요! 슬랙봇 테스트 중입니다. 이것은 고정된 응답입니다.")
    # 이벤트 중복 방지를 위한 TTL 설정 (초 단위, 기본 10분)
    EVENT_DEDUP_TTL = int(os.environ.get("EVENT_DEDUP_TTL", "600"))

    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration settings and log all settings"""
        # 모든 환경 변수 로깅
        logger.info("=== 현재 설정 ===")
        for attr in dir(cls):
            if not attr.startswith("__") and not callable(getattr(cls, attr)):
                logger.info(f"{attr}: {getattr(cls, attr)}")
        logger.info("================")
                
        required_vars = ["SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET"]
        missing = [var for var in required_vars if not getattr(cls, var)]
        if missing:
            logger.error(f"Missing required environment variables: {', '.join(missing)}")
            return False
        return True


# Initialize AWS clients
dynamodb = None
table = None
bedrock_runtime = None

# DynamoDB 초기화
if Config.USE_DYNAMODB:
    try:
        logger.info("Initializing DynamoDB client")
        dynamodb = boto3.resource("dynamodb", region_name=Config.AWS_REGION)
        table = dynamodb.Table(Config.DYNAMODB_TABLE_NAME)
        logger.info(f"DynamoDB client initialized for table: {Config.DYNAMODB_TABLE_NAME}")
    except Exception as e:
        logger.error(f"Error initializing DynamoDB: {e}", exc_info=True)
        logger.warning("DynamoDB initialization failed, will continue without DynamoDB functionality")
else:
    logger.info("DynamoDB is disabled by configuration")

# Bedrock 초기화
if Config.USE_BEDROCK:
    try:
        logger.info("Initializing Bedrock client")
        bedrock_runtime = boto3.client("bedrock-runtime", region_name=Config.AWS_REGION)
        logger.info(f"Bedrock client initialized with model: {Config.BEDROCK_MODEL_ID}")
    except Exception as e:
        logger.error(f"Error initializing Bedrock: {e}", exc_info=True)
        logger.warning("Bedrock initialization failed, will continue with test responses")
else:
    logger.info("Bedrock is disabled by configuration")

# Initialize Slack app
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

# Initialize handler for Lambda
try:
    logger.info("Initializing SlackRequestHandler")
    handler = SlackRequestHandler(app)
    logger.info("SlackRequestHandler initialized successfully")
except Exception as e:
    logger.error(f"Error initializing SlackRequestHandler: {e}", exc_info=True)
    raise

# Get Slack bot ID
bot_id = None
try:
    logger.info("Getting bot info from Slack API")
    bot_info = app.client.auth_test()
    bot_id = bot_info["user_id"]
    logger.info(f"Bot ID retrieved successfully: {bot_id}")
except Exception as e:
    logger.error(f"Error getting bot ID: {e}", exc_info=True)
    logger.warning("Bot ID retrieval failed, mention parsing may not work correctly")

# Status messages
MSG_PREVIOUS = f"이전 대화 내용 확인 중... {Config.BOT_CURSOR}"
MSG_RESPONSE = f"응답 기다리는 중... {Config.BOT_CURSOR}"
MSG_ERROR = f"오류가 발생했습니다. 잠시 후 다시 시도해주세요. {Config.BOT_CURSOR}"


class DynamoDBManager:
    """Handles DynamoDB operations for conversation context"""

    @staticmethod
    def get_context(thread_ts: Optional[str], user: str, default: str = "") -> str:
        """Retrieve conversation context from DynamoDB"""
        # DynamoDB를 사용하지 않으면 기본값 반환
        if not Config.USE_DYNAMODB or table is None:
            logger.info("DynamoDB disabled or not initialized, returning default context")
            return default
            
        try:
            logger.info(f"Getting context from DynamoDB for thread_ts={thread_ts}, user={user}")
            key = {"id": thread_ts if thread_ts else user}
            response = table.get_item(Key=key)
            logger.info(f"DynamoDB get_item response: {json.dumps(response)[:200]}...")
            
            item = response.get("Item")
            if item:
                logger.info(f"Context found in DynamoDB")
                return item["conversation"]
            else:
                logger.info(f"No context found in DynamoDB, returning default")
                return default
        except Exception as e:
            logger.error(f"Error retrieving context from DynamoDB: {e}", exc_info=True)
            return default

    @staticmethod
    def put_context(thread_ts: Optional[str], user: str, conversation: str = "", ttl_seconds: int = 3600) -> None:
        """Store conversation context in DynamoDB with TTL"""
        # DynamoDB를 사용하지 않으면 무시
        if not Config.USE_DYNAMODB or table is None:
            logger.info("DynamoDB disabled or not initialized, skipping put_context")
            return
            
        try:
            logger.info(f"Storing context in DynamoDB for thread_ts={thread_ts}, user={user}")
            expire_at = int(time.time()) + ttl_seconds  # 기본값 1시간 TTL, 하지만 인자로 변경 가능
            expire_dt = datetime.fromtimestamp(expire_at).isoformat()

            item = {
                "id": thread_ts if thread_ts else user,
                "conversation": conversation,
                "expire_dt": expire_dt,
                "expire_at": expire_at,
            }

            if thread_ts:
                item["user"] = user

            logger.info(f"Putting item to DynamoDB: {json.dumps(item)[:200]}...")
            table.put_item(Item=item)
            logger.info(f"Successfully stored context in DynamoDB")
        except Exception as e:
            logger.error(f"Error storing context in DynamoDB: {e}", exc_info=True)

    @staticmethod
    def count_user_contexts(user: str) -> int:
        """Count contexts belonging to a specific user"""
        # DynamoDB를 사용하지 않으면 0 반환
        if not Config.USE_DYNAMODB or table is None:
            logger.info("DynamoDB disabled or not initialized, returning 0 contexts")
            return 0
            
        try:
            logger.info(f"Counting contexts for user={user}")
            # Using query with a GSI would be more efficient, but for now we use scan with filter
            response = table.scan(FilterExpression=Key("user").eq(user))
            count = len(response.get("Items", []))
            logger.info(f"Found {count} contexts for user")
            return count
        except Exception as e:
            logger.error(f"Error counting contexts in DynamoDB: {e}", exc_info=True)
            return 0


class SlackManager:
    """Handles Slack messaging operations"""

    @staticmethod
    def update_message(say: Say, channel: str, thread_ts: Optional[str],
                      latest_ts: str, message: str) -> tuple:
        """Update existing message without splitting"""
        logger.info(f"Updating message in channel={channel}, thread_ts={thread_ts}, latest_ts={latest_ts}")
        try:
            # 메시지 크기 체크
            if len(message) > Config.MAX_LEN_SLACK:
                logger.warning(f"Message length ({len(message)}) exceeds Slack limit ({Config.MAX_LEN_SLACK})")
                # 메시지가 너무 긴 경우 잘라서 전송
                message = message[:Config.MAX_LEN_SLACK - 100] + "\n...(메시지가 너무 길어 일부가 생략되었습니다)..."
            
            # 메시지 업데이트
            logger.info(f"[API CALL] Updating message ts={latest_ts}")
            app.client.chat_update(channel=channel, ts=latest_ts, text=message)
            logger.info("Message updated successfully")
            
            return message, latest_ts
        except Exception as e:
            logger.error(f"Error in update_message: {e}", exc_info=True)
            # 오류 메시지로 업데이트
            try:
                logger.info(f"[API CALL] Sending error message")
                app.client.chat_update(channel=channel, ts=latest_ts, text=MSG_ERROR)
                logger.info("Error message sent successfully")
            except Exception as inner_e:
                logger.error(f"Failed to send error message: {inner_e}", exc_info=True)
            return MSG_ERROR, latest_ts

    @staticmethod
    def get_thread_history(channel: str, thread_ts: str, client_msg_id: str) -> List[str]:
        """Retrieve conversation history from a Slack thread"""
        logger.info(f"Getting thread history for channel={channel}, thread_ts={thread_ts}")
        contexts = []

        try:
            logger.info(f"[API CALL] Retrieving conversation replies")
            response = app.client.conversations_replies(channel=channel, ts=thread_ts)
            logger.info(f"Conversation replies retrieved: {len(response.get('messages', []))} messages")

            if not response.get("ok"):
                logger.error(f"Failed to retrieve thread messages: {response}")
                return contexts

            messages = response.get("messages", [])
            logger.info(f"Retrieved {len(messages)} messages from thread")
            messages.reverse()

            # Skip the thread parent message
            if messages:
                messages.pop(0)
                logger.info("Skipped parent message")

            # Process each message in the thread
            for message in messages:
                # Skip the current message being processed
                if message.get("client_msg_id") == client_msg_id:
                    logger.info(f"Skipping current message with client_msg_id={client_msg_id}")
                    continue

                # Determine role based on whether it's from a bot or user
                role = "assistant" if message.get("bot_id") else "user"
                contexts.append(f"{role}: {message.get('text', '')}")
                logger.info(f"Added message from {role}")

                # Check if we've reached the context length limit
                context_text = "\n".join(contexts)
                if len(context_text) > Config.MAX_LEN_BEDROCK:
                    logger.info(f"Context length limit reached ({len(context_text)} > {Config.MAX_LEN_BEDROCK})")
                    contexts.pop(0)  # Remove oldest message
                    break

            contexts.reverse()
            logger.info(f"Thread history processed, {len(contexts)} messages in context")

        except Exception as e:
            logger.error(f"Error retrieving thread history: {e}", exc_info=True)

        return contexts


class BedrockManager:
    """Handles Amazon Bedrock operations"""

    @staticmethod
    def invoke_model(prompt: str) -> str:
        """Invoke Amazon Bedrock model with prompt and return response"""
        if not Config.USE_BEDROCK or bedrock_runtime is None:
            logger.info("Bedrock disabled or not initialized, returning test response")
            return f"{Config.TEST_RESPONSE}\n\n요청하신 쿼리: '{prompt[:100]}'"
        
        try:
            logger.info(f"Invoking Bedrock model: {Config.BEDROCK_MODEL_ID}")
            
            # Anthropic Claude 모델 요청 형식
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            # Bedrock 모델 호출
            response = bedrock_runtime.invoke_model(
                modelId=Config.BEDROCK_MODEL_ID,
                body=json.dumps(request_body)
            )
            
            # 응답 처리
            response_body = json.loads(response.get("body").read())
            logger.info(f"Bedrock response received: {len(str(response_body))} bytes")
            
            if "content" in response_body and len(response_body.get("content", [])) > 0:
                content = response_body.get("content", [])[0].get("text", "")
                return content
            else:
                logger.error(f"Unexpected response format from Bedrock: {response_body}")
                return "죄송합니다. 응답을 처리하는 중 오류가 발생했습니다."
            
        except Exception as e:
            logger.error(f"Error invoking Bedrock model: {e}", exc_info=True)
            return f"죄송합니다. 응답을 생성하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요. (오류: {type(e).__name__})"

    @staticmethod
    def create_prompt(query: str, thread_history: Optional[List[str]] = None) -> str:
        """Create a structured prompt with XML tags for the AI model"""
        logger.info(f"Creating prompt for query: {query[:100]}")
        prompts = []
        
        # 시스템 및 개인화 메시지 추가
        prompts.append(f"User: {Config.PERSONAL_MESSAGE}")
        
        if Config.SYSTEM_MESSAGE != "None":
            prompts.append(Config.SYSTEM_MESSAGE)
        
        # 태그 기반 지시사항 추가
        prompts.append("<question> 태그로 감싸진 질문에 답변을 제공하세요.")
        
        # 대화 이력 추가
        if thread_history and len(thread_history) > 0:
            logger.info(f"Adding {len(thread_history)} messages from thread history to prompt")
            prompts.append("<history> 에 정보가 제공 되면, 대화 기록을 참고하여 답변해 주세요.")
            prompts.append("<history>")
            prompts.append("\n\n".join(thread_history))
            prompts.append("</history>")
        
        # 현재 쿼리 추가
        prompts.append("")
        prompts.append("<question>")
        prompts.append(query)
        prompts.append("</question>")
        prompts.append("")
        
        # 응답 시작 표시
        prompts.append("Assistant:")
        
        # 최종 프롬프트 생성
        final_prompt = "\n".join(prompts)
        logger.info(f"Final prompt created: {len(final_prompt)} characters")
        
        return final_prompt


def is_duplicate_event(body):
    """
    중복 이벤트 확인 함수 - 이벤트가 이미 처리된 적이 있는지 확인
    더 강력한 중복 방지 로직을 위해 여러 식별자를 조합하여 사용
    """
    try:
        # 이벤트에서 고유 식별자 추출
        event = body.get("event", {})
        event_id = body.get("event_id")
        event_time = body.get("event_time")
        client_msg_id = event.get("client_msg_id")
        user = event.get("user")
        channel = event.get("channel")
        ts = event.get("ts")
        
        # 이벤트 유형 확인
        event_type = event.get("type")
        
        # 여러 식별자를 조합하여 고유 키 생성
        unique_id_parts = [
            f"evt_{event_id or ''}",
            f"time_{event_time or ''}",
            f"msg_{client_msg_id or ''}",
            f"ch_{channel or ''}",
            f"ts_{ts or ''}",
            f"type_{event_type or ''}"
        ]
        
        # 실제 고유 ID 생성 (불필요한 부분 제거)
        unique_id = "_".join([part for part in unique_id_parts if part.split('_')[1]])
        
        logger.info(f"이벤트 고유 ID 생성됨: {unique_id}")
        
        # DynamoDB에서 이벤트 중복 여부 확인
        if Config.USE_DYNAMODB:
            context = DynamoDBManager.get_context(unique_id, "event_dedup")
            if context:
                logger.info(f"중복 이벤트 감지됨: {unique_id}")
                return True
                
            # 이벤트 처리 표시 (짧은 TTL로 설정)
            DynamoDBManager.put_context(
                unique_id, 
                "event_dedup", 
                f"processed_at_{time.time()}", 
                Config.EVENT_DEDUP_TTL
            )
            logger.info(f"이벤트 {unique_id}를 중복 방지 테이블에 기록함 (TTL: {Config.EVENT_DEDUP_TTL}초)")
        
        # 중복 아님
        return False
    except Exception as e:
        # 중복 확인 중 오류 발생 시 안전하게 처리 계속
        logger.error(f"중복 이벤트 확인 중 오류 발생: {e}", exc_info=True)
        return False
