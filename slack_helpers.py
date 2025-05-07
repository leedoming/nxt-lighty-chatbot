# slack_helpers.py
import logging
from typing import Dict, List, Optional, Any
import json

# 로거 설정
logger = logging.getLogger()

class SlackBlockManager:
    """Slack Block Kit 메시지를 관리하는 클래스"""
    
    @staticmethod
    def update_with_blocks(client, channel: str, ts: str, blocks: List[dict], 
                          text: str = None) -> bool:
        """
        Slack 메시지를 Block Kit으로 업데이트
        
        Args:
            client: Slack Web Client 인스턴스
            channel: 채널 ID
            ts: 메시지 타임스탬프
            blocks: Block Kit 블록 목록
            text: 대체 텍스트 (선택사항)
            
        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            logger.info(f"Updating message with blocks in channel={channel}, ts={ts}")
            
            if text is None:
                text = "메시지가 표시되지 않으면 Slack 앱을 업데이트해주세요."
                
            response = client.chat_update(
                channel=channel,
                ts=ts,
                blocks=blocks,
                text=text
            )
            
            logger.info("Successfully updated message with blocks")
            return True
            
        except Exception as e:
            logger.error(f"Error updating message with blocks: {e}", exc_info=True)
            return False
    
    @staticmethod
    def send_message_with_blocks(say, blocks: List[dict], text: str = None, 
                                thread_ts: str = None) -> dict:
        """
        Block Kit 형식의 새 메시지 전송
        
        Args:
            say: Slack 봇의 say 객체
            blocks: Block Kit 블록 목록
            text: 대체 텍스트 (선택사항)
            thread_ts: 스레드 타임스탬프 (스레드 내 응답인 경우)
            
        Returns:
            dict: Slack API 응답
        """
        try:
            logger.info(f"Sending new message with blocks, thread_ts={thread_ts}")
            
            if text is None:
                text = "메시지가 표시되지 않으면 Slack 앱을 업데이트해주세요."
                
            return say(
                blocks=blocks,
                text=text,
                thread_ts=thread_ts
            )
            
        except Exception as e:
            logger.error(f"Error sending message with blocks: {e}", exc_info=True)
            # 오류 시 일반 텍스트로 전송 시도
            return say(text=text or "메시지 전송 중 오류가 발생했습니다.", thread_ts=thread_ts)
    
    @staticmethod
    def store_original_message(db_manager, key: str, user: str, 
                              parsed_data: dict, blocks: List[dict]) -> bool:
        """
        원본 메시지를 DB에 저장 (돌아가기 기능용)
        
        Args:
            db_manager: DynamoDB 매니저 인스턴스
            key: 메시지 키 (일반적으로 thread_ts 또는 ts)
            user: 사용자 ID
            parsed_data: 파싱된 응답 데이터
            blocks: 생성된 Block Kit 블록
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            logger.info(f"Storing original message data for key={key}, user={user}")
            
            # 저장할 데이터 구성
            message_data = {
                "parsed_data": parsed_data,
                "blocks": blocks
            }
            
            # JSON으로 직렬화
            serialized_data = json.dumps(message_data)
            
            # 저장 (DynamoDB 매니저 사용)
            db_manager.put_context(key, user, serialized_data)
            
            logger.info("Successfully stored original message data")
            return True
            
        except Exception as e:
            logger.error(f"Error storing original message: {e}", exc_info=True)
            return False
    
    @staticmethod
    def retrieve_original_message(db_manager, key: str, user: str) -> Optional[dict]:
        """
        DB에서 원본 메시지 검색 (돌아가기 기능용)
        
        Args:
            db_manager: DynamoDB 매니저 인스턴스
            key: 메시지 키 (일반적으로 thread_ts 또는 ts)
            user: 사용자 ID
            
        Returns:
            Optional[dict]: 원본 메시지 데이터 또는 None (오류 시)
        """
        try:
            logger.info(f"Retrieving original message data for key={key}, user={user}")
            
            # DB에서 데이터 가져오기
            serialized_data = db_manager.get_context(key, user)
            
            if not serialized_data:
                logger.warning(f"No original message found for key={key}")
                return None
                
            # JSON 역직렬화
            message_data = json.loads(serialized_data)
            
            logger.info("Successfully retrieved original message data")
            return message_data
            
        except Exception as e:
            logger.error(f"Error retrieving original message: {e}", exc_info=True)
            return None