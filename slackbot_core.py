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
    
    # Agent configuration
    AGENT_ID = os.environ.get("AGENT_ID", "MLARXNITGT")
    AGENT_ALIAS_ID = os.environ.get("AGENT_ALIAS_ID", "2GOMEHFYNM")
    USE_AGENT = os.environ.get("USE_AGENT", "true").lower() == "true"
    
    # 디버깅을 위해 DynamoDB 사용 여부를 제어하는 플래그
    USE_DYNAMODB = os.environ.get("USE_DYNAMODB", "true").lower() == "true"
    USE_BEDROCK = os.environ.get("USE_BEDROCK", "true").lower() == "true"
    # 테스트용 응답
    TEST_RESPONSE = os.environ.get("TEST_RESPONSE", "안녕하세요! 슬랙봇 테스트 중입니다. 이것은 고정된 응답입니다.")
    # 이벤트 중복 방지를 위한 TTL 설정 (초 단위, 기본 10분)
    EVENT_DEDUP_TTL = int(os.environ.get("EVENT_DEDUP_TTL", "600"))
    # 슬랙 응답 사이 간격 (초)
    SLACK_SAY_INTERVAL = float(os.environ.get("SLACK_SAY_INTERVAL", "0"))

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
bedrock_agent_runtime = None

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

# Bedrock 및 Bedrock Agent 초기화
if Config.USE_BEDROCK:
    try:
        logger.info("Initializing Bedrock clients")
        
        # Standard Bedrock runtime client for model inference
        bedrock_runtime = boto3.client("bedrock-runtime", region_name=Config.AWS_REGION)
        logger.info(f"Bedrock runtime client initialized with model: {Config.BEDROCK_MODEL_ID}")
        
        # Bedrock Agent runtime client for agent invocation
        bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=Config.AWS_REGION)
        logger.info(f"Bedrock Agent runtime client initialized with agent: {Config.AGENT_ID}")
    except Exception as e:
        logger.error(f"Error initializing Bedrock clients: {e}", exc_info=True)
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


class MessageFormatter:
    """Handles message formatting and splitting for Slack"""

    @staticmethod
    def split_message(message: str, max_len: int) -> List[str]:
        """Split a message into chunks that fit within max_len"""
        # If message is empty or smaller than max_len, return as is
        if not message or len(message) <= max_len:
            return [message]

        # First split by code blocks
        parts = []
        segments = message.split("```")

        for i, segment in enumerate(segments):
            if not segment:  # Skip empty segments
                continue

            if i % 2 == 1:  # This is a code block
                # Preserve the code block formatting
                code_parts = MessageFormatter._split_text(f"```{segment}```", max_len)
                parts.extend(code_parts)
            else:
                # Regular text - split by paragraphs
                text_parts = MessageFormatter._split_text(segment, max_len)
                parts.extend(text_parts)

        # Final cleanup to ensure no part exceeds max_len
        result = []
        current = ""

        for part in parts:
            if len(current) + len(part) + 2 <= max_len:
                if current:
                    current += "\n\n" + part
                else:
                    current = part
            else:
                if current:
                    result.append(current)
                current = part

        if current:
            result.append(current)

        return result

    @staticmethod
    def _split_text(text: str, max_len: int) -> List[str]:
        """Helper method to split text by paragraphs"""
        if len(text) <= max_len:
            return [text]

        parts = text.split("\n\n")
        result = []
        current = ""

        for part in parts:
            # If a single part is longer than max_len, split it by sentences
            if len(part) > max_len:
                sentences = re.split(r'(?<=[.!?])\s+', part)
                for sentence in sentences:
                    if len(current) + len(sentence) + 2 <= max_len:
                        if current:
                            current += " " + sentence
                        else:
                            current = sentence
                    else:
                        if current:
                            result.append(current)
                        current = sentence
            elif len(current) + len(part) + 2 <= max_len:
                if current:
                    current += "\n\n" + part
                else:
                    current = part
            else:
                if current:
                    result.append(current)
                current = part

        if current:
            result.append(current)

        return result


class SlackManager:
    """Handles Slack messaging operations"""

    @staticmethod
    def update_message(say: Say, channel: str, thread_ts: Optional[str],
                      latest_ts: str, message: str) -> tuple:
        """Update existing message and send additional messages if needed"""
        logger.info(f"Updating message in channel={channel}, thread_ts={thread_ts}, latest_ts={latest_ts}")
        try:
            split_messages = MessageFormatter.split_message(message, Config.MAX_LEN_SLACK)
            logger.info(f"Message split into {len(split_messages)} parts")

            for i, text in enumerate(split_messages):
                if i == 0:
                    # Update the initial message
                    logger.info(f"[API CALL] Updating first message ts={latest_ts}")
                    app.client.chat_update(channel=channel, ts=latest_ts, text=text)
                    logger.info("First message updated successfully")
                else:
                    # Add delay if configured
                    if Config.SLACK_SAY_INTERVAL > 0:
                        logger.info(f"Waiting {Config.SLACK_SAY_INTERVAL}s before sending next message")
                        time.sleep(Config.SLACK_SAY_INTERVAL)

                    # Send additional messages in thread
                    logger.info(f"[API CALL] Sending additional message part {i+1}")
                    result = say(text=text, thread_ts=thread_ts)
                    latest_ts = result["ts"]
                    logger.info(f"Additional message sent, ts={latest_ts}")

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
    def invoke_agent(prompt: str) -> str:
        """Invoke Amazon Bedrock Agent with prompt and return response"""
        if not Config.USE_BEDROCK or bedrock_agent_runtime is None:
            logger.info("Bedrock Agent disabled or not initialized, returning test response")
            return f"{Config.TEST_RESPONSE}\n\n요청하신 쿼리: '{prompt[:100]}'"
        
        try:
            # Create a unique session ID
            now = datetime.now()
            session_id = str(int(now.timestamp() * 1000))
            
            logger.info(f"Invoking Bedrock Agent: {Config.AGENT_ID} with alias: {Config.AGENT_ALIAS_ID}")
            logger.info(f"Session ID: {session_id}")
            
            # Call Bedrock Agent
            response = bedrock_agent_runtime.invoke_agent(
                agentId=Config.AGENT_ID,
                agentAliasId=Config.AGENT_ALIAS_ID,
                sessionId=session_id,
                inputText=prompt,
            )
            
            # Process streaming response
            completion = ""
            for event in response.get("completion"):
                chunk = event["chunk"]
                completion += chunk["bytes"].decode()
                
            logger.info(f"Bedrock Agent response received: {len(completion)} characters")
            return completion

        except Exception as e:
            logger.error(f"Error invoking Bedrock Agent: {e}", exc_info=True)
            return f"죄송합니다. 응답을 생성하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요. (오류: {type(e).__name__})"

    @staticmethod
    def create_prompt(query: str, thread_history: Optional[List[str]] = None) -> str:
        """Create a structured prompt with XML tags for the AI model"""
        logger.info(f"Creating prompt for query: {query[:100]}")
        prompts = []
        
        # 시스템 및 개인화 메시지 추가
        prompts.append("당신은 마스코트 '라이티(Lighty)'입니다. '광주대학교'의 Slack 채팅방에서 활동하는 전문적이고 친근한 광주대 마스코트입니다.")
        prompts.append("따뜻하고, 친근하며, 전문적인 방식으로 이모지를 섞어 메시지에 응답하세요.")
        prompts.append(f"User: {Config.PERSONAL_MESSAGE}")
        
        if Config.SYSTEM_MESSAGE != "None":
            prompts.append(Config.SYSTEM_MESSAGE)
        
        # 태그 기반 지시사항 추가
        prompts.append("")
        
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
        logger.info("Step 4: Creating prompt and getting response")
        prompt = BedrockManager.create_prompt(query, thread_history)
        
        # 응답 생성 - Bedrock Agent 또는 모델 사용
        if Config.USE_AGENT and bedrock_agent_runtime is not None:
            # Bedrock Agent를 사용하여 응답 생성
            logger.info("Using Bedrock Agent for response generation")
            message = BedrockManager.invoke_agent(prompt)
        else:
            # 일반 Bedrock 모델 사용
            logger.info("Using standard Bedrock model for response generation")
            message = BedrockManager.invoke_model(prompt)
            
        logger.info(f"Response message generated: {len(message)} characters")

        # 메시지 데이터베이스에 저장 (선택적)
        if user and Config.USE_DYNAMODB:
            logger.info(f"Storing conversation in DynamoDB for user: {user}")
            try:
                DynamoDBManager.put_context(thread_ts, user, f"query: {query}, response: {message[:100]}...")
            except Exception as e:
                logger.error(f"Error storing conversation in DynamoDB: {e}", exc_info=True)
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
