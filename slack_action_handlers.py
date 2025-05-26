# slack_action_handlers.py
"""
Slack 액션 이벤트 핸들러 모듈
"""
import logging
import json
from typing import Dict, Any

from constants import DEPARTMENT_INFO
from config import Config
from aws_clients import DynamoDBManager

logger = logging.getLogger()

class SlackActionHandler:
    """Slack 액션 이벤트 핸들러 클래스"""
    
    def __init__(self, app, response_parser):
        """
        생성자
        
        Args:
            app: Slack App 인스턴스
            response_parser: 응답 파서
        """
        self.app = app
        self.response_parser = response_parser
        
        # 핸들러 등록
        self.register_handlers()
    
    def register_handlers(self):
        """액션 핸들러 등록"""
        self.app.action("show_department")(self.handle_department_button)
        self.app.action("back_to_original")(self.handle_back_button)
        self.app.action(".*")(self.log_any_action)  # 모든 액션 로깅
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
            
            # 현재 메시지의 블록과 텍스트 가져오기
            current_blocks = body["message"].get("blocks", [])
            current_text = body["message"].get("text", "")
            
            # 원본 메시지가 아직 저장되지 않았다면 저장
            if DynamoDBManager.get_context(message_key, user_id) == "":
                # 블록과 원본 메시지를 저장
                DynamoDBManager.put_context(
                    message_key, 
                    user_id, 
                    json.dumps({
                        "blocks": current_blocks, 
                        "text": current_text,
                        "department": department_name
                    })
                )
                logger.info(f"원본 메시지 저장 완료: {message_key}")
            
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
            # 사용자에게 오류 메시지 표시
            try:
                client.chat_postEphemeral(
                    channel=body["channel"]["id"],
                    user=body["user"]["id"],
                    text="부서 정보를 표시하는 중 오류가 발생했습니다."
                )
            except:
                pass
    
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
            original_data_str = DynamoDBManager.get_context(message_key, user_id)
            logger.info(f"가져온 원본 데이터 길이: {len(original_data_str) if original_data_str else 0}")
            
            if original_data_str and original_data_str != "":
                try:
                    # JSON 파싱
                    logger.info("원본 데이터 JSON 파싱 시도")
                    original_data = json.loads(original_data_str)
                    logger.info("원본 데이터 파싱 성공")
                    
                    # 데이터 형식 파악을 위한 키 확인
                    keys = list(original_data.keys())
                    logger.info(f"원본 데이터 키: {keys}")
                    
                    # 블록과 텍스트가 있는 경우 (현재 형식)
                    if "blocks" in original_data and "text" in original_data:
                        logger.info("원본 메시지에 blocks와 text가 있는 형식 감지")
                        
                        # 메시지 업데이트
                        client.chat_update(
                            channel=channel_id,
                            ts=message_ts,
                            blocks=original_data["blocks"],
                            text=original_data["text"]
                        )
                        
                        logger.info("원본 메시지로 복원 성공")
                        return
                    
                    # 다른 알려진 형식 처리
                    if "parsed_data" in original_data:
                        logger.info("parsed_data 형식의 메시지입니다.")
                        # slack_block_manager가 저장한 형식
                        client.chat_update(
                            channel=channel_id,
                            ts=message_ts,
                            blocks=original_data.get("blocks", []),
                            text=original_data.get("parsed_data", {}).get("contents", "원본 응답으로 돌아왔습니다.")
                        )
                        logger.info("parsed_data 형식 메시지 복원 성공")
                        return
                    
                    # department만 있는 경우 (이전 형식)
                    if "department" in original_data and not "blocks" in original_data:
                        logger.info("department 정보만 있는 메시지입니다.")
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
                        logger.info("department 정보로 대체 메시지 복원 성공")
                        return
                    
                    # 알 수 없는 형식인 경우
                    logger.warning(f"알 수 없는 데이터 형식입니다: {str(original_data)[:100]}...")
                    default_blocks = [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "원본 메시지로 돌아왔습니다.\n\n추가 질문이 있으시면 말씀해주세요."
                            }
                        }
                    ]
                    
                    client.chat_update(
                        channel=channel_id,
                        ts=message_ts,
                        blocks=default_blocks,
                        text="원본 응답으로 돌아왔습니다."
                    )
                    logger.info("알 수 없는 형식이라 기본 메시지로 복원")
                    
                except json.JSONDecodeError as json_err:
                    logger.error(f"원본 메시지 데이터 파싱 오류: {json_err}", exc_info=True)
                    # 기본 블록으로 돌아가기
                    default_blocks = [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "원본 응답을 파싱할 수 없어 기본 화면으로 돌아갑니다."
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
                logger.warning(f"원본 메시지 데이터를 찾을 수 없음: key={message_key}")
                # 기본 블록으로 돌아가기
                default_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "원본 응답을 찾을 수 없어 기본 화면으로 돌아갑니다.\n더 필요한 정보가 있으시면 새로운 질문을 입력해 주세요."
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
            try:
                client.chat_postEphemeral(
                    channel=body["channel"]["id"],
                    user=body["user"]["id"], 
                    text="이전 화면으로 돌아가는 중 오류가 발생했습니다."
                )
            except Exception as inner_e:
                logger.error(f"에러 메시지 전송 중 추가 오류: {str(inner_e)}")
    
    def log_any_action(self, ack, body):
        """모든 액션을 로깅하는 핸들러"""
        # 먼저 이벤트 승인 (중요)
        ack()
        
        try:
            logger.info("=== 액션 이벤트 수신! ===")
            logger.info(f"액션 ID: {body['actions'][0]['action_id']}")
            logger.info(f"액션 값: {body['actions'][0].get('value', '없음')}")
            logger.info(f"사용자: {body['user']['id']}")
            logger.info(f"채널: {body['channel']['id']}")
            logger.info(f"메시지 TS: {body['message']['ts']}")
            logger.info("===========================")
        except Exception as e:
            logger.error(f"액션 로깅 오류: {e}")