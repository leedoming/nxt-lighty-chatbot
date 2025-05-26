# slack_manager.py
"""
Slack 메시지 송수신 및 히스토리 관리
"""
import logging
import time
from typing import List, Optional, Tuple, Dict, Any
from slack_bolt import Say

from config import Config
from message_formatter import MessageFormatter

logger = logging.getLogger()

class SlackManager:
    """Slack 메시지 작업 처리"""

    @staticmethod
    def update_message(say: Say, channel: str, thread_ts: Optional[str],
                      latest_ts: str, message: str, client=None) -> Tuple[str, str]:
        """
        기존 메시지 업데이트 및 필요시 추가 메시지 전송
        
        Args:
            say: Slack 봇의 say 객체
            channel: 채널 ID
            thread_ts: 스레드 TS (스레드 내 응답인 경우)
            latest_ts: 최신 메시지의 TS
            message: 전송할 메시지 텍스트
            client: Slack 클라이언트 객체
            
        Returns:
            tuple: (업데이트된 메시지, 최신 메시지 TS)
        """
        logger.info(f"Updating message in channel={channel}, thread_ts={thread_ts}, latest_ts={latest_ts}")
        
        # client 객체가 None인지 확인
        if client is None:
            logger.error("Slack client is not provided")
            return message, latest_ts

        # 메시지가 빈 문자열이거나 None인 경우 기본 메시지 설정
        if not message or not message.strip():
            logger.warning("Empty message detected, setting default text")
            message = "처리 중입니다..."
        
        try:
            split_messages = MessageFormatter.split_message(message, Config.MAX_LEN_SLACK)
            logger.info(f"Message split into {len(split_messages)} parts")

            for i, text in enumerate(split_messages):
                # 각 메시지 파트가 비어있지 않은지 확인
                if not text or not text.strip():
                    logger.warning(f"Empty text part {i}, skipping")
                    continue
                    
                if i == 0:
                    # Update the initial message
                    logger.info(f"[API CALL] Updating first message ts={latest_ts}")
                    try:
                        client.chat_update(
                            channel=channel, 
                            ts=latest_ts, 
                            text=text.strip()  # 공백 제거
                        )
                        logger.info("First message updated successfully")
                    except Exception as update_err:
                        logger.error(f"Error updating message: {update_err}")
                        # 업데이트 실패 시 에러 메시지로 재시도
                        try:
                            client.chat_update(
                                channel=channel, 
                                ts=latest_ts, 
                                text="메시지 업데이트 중 오류가 발생했습니다."
                            )
                        except:
                            pass
                        raise update_err
                else:
                    # Add delay if configured
                    if Config.SLACK_SAY_INTERVAL > 0:
                        logger.info(f"Waiting {Config.SLACK_SAY_INTERVAL}s before sending next message")
                        time.sleep(Config.SLACK_SAY_INTERVAL)

                    # Send additional messages in thread
                    logger.info(f"[API CALL] Sending additional message part {i+1}")
                    result = say(text=text.strip(), thread_ts=thread_ts)
                    latest_ts = result["ts"]
                    logger.info(f"Additional message sent, ts={latest_ts}")

            return message, latest_ts
            
        except Exception as e:
            logger.error(f"Error in update_message: {e}", exc_info=True)
            # 오류 메시지로 업데이트
            try:
                logger.info(f"[API CALL] Sending error message")
                client.chat_update(
                    channel=channel, 
                    ts=latest_ts, 
                    text=Config.STATUS_ERROR
                )
                logger.info("Error message sent successfully")
            except Exception as inner_e:
                logger.error(f"Failed to send error message: {inner_e}", exc_info=True)
            return Config.STATUS_ERROR, latest_ts

    @staticmethod
    def get_thread_history(channel: str, thread_ts: str, client_msg_id: str, app) -> List[str]:
        """
        Slack 스레드에서 대화 히스토리 검색
        
        Args:
            channel: 채널 ID
            thread_ts: 스레드 TS
            client_msg_id: 현재 처리 중인 메시지의 client_msg_id
            app: Slack App 인스턴스
            
        Returns:
            List[str]: 컨텍스트 메시지 목록
        """
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
    
    @staticmethod
    def get_dm_history(channel: str, client_msg_id: str, app, limit: int = 10) -> List[str]:
        """
        DM 채널에서 대화 히스토리 검색 (최근 몇 개 대화만)
        
        Args:
            channel: 채널 ID
            client_msg_id: 현재 처리 중인 메시지의 client_msg_id
            app: Slack App 인스턴스
            limit: 가져올 메시지 수 제한
            
        Returns:
            List[str]: 컨텍스트 메시지 목록
        """
        logger.info(f"Getting DM history for channel={channel}")
        contexts = []

        try:
            logger.info(f"[API CALL] Retrieving DM conversation history")
            response = app.client.conversations_history(
                channel=channel, 
                limit=limit,  # 조금 여유있게 가져와서 필터링
                include_all_metadata=True
            )
            logger.info(f"DM history retrieved: {len(response.get('messages', []))} messages")

            if not response.get("ok"):
                logger.error(f"Failed to retrieve DM messages: {response}")
                return contexts

            messages = response.get("messages", [])
            logger.info(f"Retrieved {len(messages)} messages from DM")
            
            # 메시지를 시간순으로 정렬 (오래된 것부터)
            messages = sorted(messages, key=lambda x: float(x.get('ts', '0')))

            # 대화 쌍을 저장할 리스트
            conversation_pairs = []
            
            # 현재 처리 중인 메시지 이후의 유효한 대화 쌍만 찾기
            found_current = False
            
            for i, message in enumerate(messages):
                # 현재 처리 중인 메시지는 건너뛰기
                if message.get("client_msg_id") == client_msg_id:
                    found_current = True
                    continue
                    
                # 현재 메시지를 찾기 전의 메시지들만 처리
                if found_current:
                    break
                
                # 사용자 메시지인지 확인
                if not message.get("bot_id") and message.get("text"):
                    user_message = message.get("text")
                    
                    # 다음 메시지가 봇 응답인지 확인
                    if i + 1 < len(messages):
                        next_message = messages[i + 1]
                        if next_message.get("bot_id") and next_message.get("text"):
                            bot_response = next_message.get("text")
                            conversation_pairs.append((user_message, bot_response))
                            logger.info(f"Found conversation pair: user message + bot response")
            
            # 최근 3개 대화만 선택
            recent_pairs = conversation_pairs[-3:] if len(conversation_pairs) > 3 else conversation_pairs
            
            # 대화 쌍을 컨텍스트 형식으로 변환
            for user_msg, bot_msg in recent_pairs:
                contexts.append(f"user: {user_msg}")
                contexts.append(f"assistant: {bot_msg}")
            
            logger.info(f"DM history processed, {len(contexts)//2} conversation pairs in context")

        except Exception as e:
            logger.error(f"Error retrieving DM history: {e}", exc_info=True)

        return contexts