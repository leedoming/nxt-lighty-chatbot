# conversation_handler.py
"""
대화 처리 및 응답 생성 모듈 - 업데이트됨
"""
import logging
import time
import traceback
import json
from typing import Optional, List

from slack_bolt import Say

from config import Config
from aws_clients import DynamoDBManager
from bedrock_manager import BedrockManager
from slack_manager import SlackManager
from response_parser import ResponseParser
from slack_helpers import SlackBlockManager

logger = logging.getLogger()

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

def conversation(app, say, query: str, thread_ts: Optional[str] = None,
               channel: Optional[str] = None, client_msg_id: Optional[str] = None,
               user: Optional[str] = None) -> None:
    """
    메인 대화 처리기 - 쿼리를 처리하고 응답을 반환
    
    Args:
        app: Slack App 인스턴스
        say: Slack 봇의 say 객체
        query: 사용자 질문
        thread_ts: 스레드 TS (선택사항)
        channel: 채널 ID (선택사항)
        client_msg_id: 클라이언트 메시지 ID (선택사항)
        user: 사용자 ID (선택사항)
    """
    logger.info(f"Starting conversation handler - query: {query}, channel: {channel}, thread_ts: {thread_ts}")

    # 의존성 초기화 - Slack 클라이언트를 ResponseParser에 전달
    response_parser = ResponseParser(slack_client=app.client)
    slack_block_manager = SlackBlockManager()

    # 변수 초기화
    message = ""
    raw_message = ""

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
        
        # 디엠인지 확인 - channel이 'D'로 시작하는지 확인
        is_dm = channel and channel.startswith('D')
        logger.info(f"Channel type check: is_dm={is_dm}, channel={channel}")
        
        if thread_ts or is_dm:  # 스레드가 있거나 디엠일 때 이전 대화 조회
            logger.info("Step 2: Getting conversation history")
            try:
                # 이전 메시지 확인 중 상태 업데이트
                logger.info("Updating with 'getting previous messages' status")
                SlackManager.update_message(say, channel, thread_ts, latest_ts, Config.STATUS_PREVIOUS)
                
                if is_dm:
                    # 디엠의 경우 채널 전체 history 조회
                    logger.info("Retrieving DM history...")
                    thread_history = SlackManager.get_dm_history(channel, client_msg_id, app)
                else:
                    # 스레드의 경우 기존 방식 사용
                    logger.info("Retrieving thread history...")
                    thread_history = SlackManager.get_thread_history(channel, thread_ts, client_msg_id, app)
                    
                logger.info(f"Conversation history retrieved, {len(thread_history)} messages")
                
                # 디버깅용: 가져온 히스토리 내용 로그
                if thread_history:
                    logger.info(f"First history item: {thread_history[0][:100]}...")
                else:
                    logger.info("No history found")
                    
            except Exception as e:
                logger.error(f"Error getting conversation history: {e}", exc_info=True)
                # 히스토리 실패는 치명적이지 않음 - 계속 진행
        else:
            logger.info("Step 2: No thread_ts or DM, skipping conversation history")

        # 응답 생성 중 상태 업데이트 (Step 3)
        logger.info("Step 3: Updating with 'processing' status")
        try:
            SlackManager.update_message(say, channel, thread_ts, latest_ts, Config.STATUS_RESPONSE, app.client)
            logger.info("Processing status updated successfully")
        except Exception as e:
            logger.error(f"Error updating processing status: {e}", exc_info=True)
            # 계속 진행 시도
        
        # 프롬프트 생성 시 히스토리 여부 확인
        logger.info("Step 4: Creating prompt and getting response")
        prompt = BedrockManager.create_prompt(query, thread_history)
        
        # 응답 생성 - Bedrock Agent 또는 모델 사용
        logger.info("Step 5: Getting response from Bedrock")
        if Config.USE_AGENT and True:  # bedrock_agent_runtime이 있는지 체크 대신 True 사용
            # Bedrock Agent를 사용하여 응답 생성
            logger.info("Using Bedrock Agent for response generation")
            try:
                raw_message = BedrockManager.invoke_agent(prompt)
                logger.info(f"Raw message received from Agent, length: {len(raw_message)}")
                
                # 빈 응답 체크
                if not raw_message or not raw_message.strip():
                    logger.warning("Bedrock Agent returned empty response")
                    raw_message = "죄송합니다. 응답이 생성되지 않았습니다. 질문을 다시 입력해주세요."
                
            except Exception as agent_error:
                logger.error(f"Bedrock Agent error: {agent_error}", exc_info=True)
                # Agent 실패 시 폴백 메시지
                raw_message = "죄송합니다. 현재 서비스에 일시적인 문제가 있습니다. 잠시 후 다시 시도해주세요."
            
            try:
                # 태그 파싱 및 블록 생성
                logger.info("Parsing agent response...")
                parsed_data = response_parser.parse_agent_response(raw_message)
                logger.info(f"Parsed data: intro={len(parsed_data.get('intro', ''))}, contents={len(parsed_data.get('contents', ''))}, department={parsed_data.get('department', '')}")
                
                blocks = response_parser.create_slack_blocks(parsed_data)
                logger.info(f"Created {len(blocks)} Slack blocks")
                
                # 원본 데이터 저장 (돌아가기 기능용)
                message_key = f"original_{latest_ts}"
                slack_block_manager.store_original_message(
                    DynamoDBManager, 
                    message_key, 
                    user or "anonymous", 
                    parsed_data, 
                    blocks
                )
                
                # 일반 텍스트 버전 생성 (블록과 함께 제공)
                plain_text = response_parser.get_plain_text_fallback(parsed_data)
                logger.info(f"Plain text version length: {len(plain_text)}")
                
                # ResponseParser의 update_message 메서드 사용
                logger.info("Updating message with blocks using ResponseParser...")
                try:
                    response_parser.update_message(
                        channel=channel,
                        ts=latest_ts,
                        text=plain_text,  # 항상 유효한 text 값 전달
                        thread_ts=thread_ts if thread_ts != latest_ts else None,
                        blocks=blocks
                    )
                    logger.info("Successfully updated message with interactive blocks using ResponseParser")
                    message = raw_message  # DynamoDB 저장용
                    
                except Exception as update_error:
                    logger.error(f"Error updating with ResponseParser: {update_error}", exc_info=True)
                    # ResponseParser 업데이트 실패 시 기존 SlackManager로 폴백
                    logger.warning("Falling back to SlackManager for message update")
                    message = plain_text
                    SlackManager.update_message(
                        say, 
                        channel, 
                        thread_ts, 
                        latest_ts, 
                        message
                    )
                    
            except Exception as parsing_error:
                logger.error(f"Error parsing/formatting response: {parsing_error}", exc_info=True)
                # 파싱 실패 시 원본 메시지 그대로 표시
                message = raw_message if raw_message else "처리 중 오류가 발생했습니다."
                logger.info("Falling back to raw message due to parsing error")
                SlackManager.update_message(say, channel, thread_ts, latest_ts, message)
        else:
            # 일반 Bedrock 모델 사용
            logger.info("Using standard Bedrock model for response generation")
            message = BedrockManager.invoke_model(prompt)
            logger.info(f"Response message generated: {len(message)} characters")
            
            # 최종 응답 전송 (일반 텍스트)
            final_message, final_ts = SlackManager.update_message(
                say, channel, thread_ts, latest_ts, message
            )
            
        # 메시지 데이터베이스에 저장
        if user and Config.USE_DYNAMODB:
            is_dm = channel and channel.startswith('D')
            context_key = thread_ts if thread_ts else (f"dm_{channel}" if is_dm else user)
            logger.info(f"Storing conversation in DynamoDB for context_key: {context_key}")
            try:
                # message가 있는지 확인하고 저장
                if message and message.strip():
                    DynamoDBManager.put_context(context_key, user, f"query: {query}, response: {message[:100]}...")
                else:
                    logger.warning("No message to store in DynamoDB")
            except Exception as e:
                logger.error(f"Error storing conversation in DynamoDB: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Error in conversation handler: {e}", exc_info=True)
        logger.error(f"Full stack trace: {traceback.format_exc()}")
        # Update with error message if possible
        try:
            if 'latest_ts' in locals():
                logger.info("Attempting to send error message to user")
                SlackManager.update_message(say, channel, thread_ts, latest_ts, Config.STATUS_ERROR)
                logger.info("Error message sent to user successfully")
        except Exception as inner_e:
            logger.error(f"Failed to send error message: {inner_e}", exc_info=True)