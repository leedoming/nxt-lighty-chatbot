# slack_action_handler.py
import logging
import json
from typing import Dict, List, Optional, Any

# 로거 설정
logger = logging.getLogger()

class SlackActionHandler:
    """Slack 액션 이벤트 핸들러 클래스"""
    
    def __init__(self, app, db_manager, response_parser):
        """
        생성자
        
        Args:
            app: Slack App 인스턴스
            db_manager: DynamoDB 매니저
            response_parser: 응답 파서
        """
        self.app = app
        self.db_manager = db_manager
        self.response_parser = response_parser
        
        # 핸들러 등록
        self.register_handlers()
    
    def register_handlers(self):
        """액션 핸들러 등록"""
        self.app.action("show_department")(self.handle_department_button)
        self.app.action("back_to_original")(self.handle_back_button)
        logger.info("Registered Slack action handlers")
    
    def handle_department_button(self, ack, body, client):
        """부서 정보 버튼 클릭 처리"""
        # 이벤트 승인
        ack()
        
        try:
            logger.info("Handling show_department button click")
            
            # 버튼 값에서 부서 이름 추출
            action = body["actions"][0]
            department_value = action["value"]
            department_name = department_value.replace("department_", "")
            
            # 메시지 정보
            channel_id = body["channel"]["id"]
            message_ts = body["message"]["ts"]
            user_id = body["user"]["id"]
            
            # 원본 메시지를 저장하기 위한 키 생성
            message_key = f"original_{message_ts}"
            
            # 원본 메시지가 아직 저장되지 않았다면 저장
            if self.db_manager.get_context(message_key, user_id) == "":
                # 블록과 원본 메시지를 저장
                self.db_manager.put_context(
                    message_key, 
                    user_id, 
                    json.dumps({"message_ts": message_ts, "department": department_name})
                )
            
            # 부서 정보 화면용 블록 생성
            department_blocks = self.response_parser.create_department_view(department_name)
            
            # 메시지 업데이트
            client.chat_update(
                channel=channel_id,
                ts=message_ts,
                blocks=department_blocks,
                text=f"{department_name} 부서 정보"
            )
            
            logger.info(f"Successfully updated message to show department view for {department_name}")
            
        except Exception as e:
            logger.error(f"Error handling department button: {e}", exc_info=True)
    
    def handle_back_button(self, ack, body, client):
        """돌아가기 버튼 클릭 처리"""
        # 이벤트 승인
        ack()
        
        try:
            logger.info("Handling back_to_original button click")
            
            # 메시지 정보
            channel_id = body["channel"]["id"]
            message_ts = body["message"]["ts"]
            user_id = body["user"]["id"]
            
            # 원본 메시지 키
            message_key = f"original_{message_ts}"
            
            # DB에서 원본 메시지 데이터 검색
            original_data_str = self.db_manager.get_context(message_key, user_id)
            
            if original_data_str:
                try:
                    # JSON 파싱
                    original_data = json.loads(original_data_str)
                    
                    # 간단한 대체 블록
                    blocks = [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*원본 응답으로 돌아왔습니다.*\n\n{original_data.get('department', '')}에 대한 정보를 확인하셨습니다."
                            }
                        }
                    ]
                    
                    # 메시지 업데이트
                    client.chat_update(
                        channel=channel_id,
                        ts=message_ts,
                        blocks=blocks,
                        text="원본 응답으로 돌아왔습니다."
                    )
                    
                    logger.info("Successfully returned to original view")
                    
                except json.JSONDecodeError:
                    logger.error(f"Error parsing original message data: {original_data_str}")
                    # 기본 블록으로 돌아가기
                    default_blocks = [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "원본 응답을 찾을 수 없어 기본 화면으로 돌아갑니다."
                            }
                        }
                    ]
                    
                    client.chat_update(
                        channel=channel_id,
                        ts=message_ts,
                        blocks=default_blocks,
                        text="원본 응답으로 돌아가기 실패"
                    )
            else:
                logger.warning(f"No original message data found for key={message_key}")
                # 기본 블록으로 돌아가기
                default_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "원본 응답을 찾을 수 없어 기본 화면으로 돌아갑니다."
                        }
                    }
                ]
                
                client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    blocks=default_blocks,
                    text="원본 응답으로 돌아가기 실패"
                )
            
        except Exception as e:
            logger.error(f"Error handling back button: {e}", exc_info=True)