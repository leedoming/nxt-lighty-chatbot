# response_parser.py
"""
Bedrock Agent 응답을 파싱하고 Slack 메시지 형태로 변환하는 모듈
"""
import re
import logging
from typing import Dict, List, Optional, Any
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from constants import DEPARTMENT_INFO

# 로거 설정
logger = logging.getLogger()

class ResponseParser:
    """Bedrock Agent 응답을 파싱하고 Slack 메시지 형태로 변환하는 클래스"""
    
    def __init__(self, slack_client: Optional[WebClient] = None):
        """
        ResponseParser 초기화
        
        Args:
            slack_client: Slack WebClient 인스턴스 (선택사항)
        """
        self.slack_client = slack_client
        
    def set_slack_client(self, slack_client: WebClient):
        """Slack 클라이언트 설정"""
        self.slack_client = slack_client
    
    @staticmethod
    def parse_agent_response(response: str) -> dict:
        """
        Bedrock Agent 응답에서 태그를 추출하여 구조화된 데이터로 변환
        
        Args:
            response: Bedrock Agent의 원본 응답
            
        Returns:
            dict: 파싱된 데이터 구조
        """
        logger.info(f"Parsing agent response: {len(response)} characters")
        
        parsed_data = {
            "intro": "",
            "contents": "",
            "department": ""
        }
        
        try:
            # 정규식으로 태그 내용 추출
            intro_match = re.search(r'<intro>(.*?)</intro>', response, re.DOTALL)
            if intro_match:
                parsed_data["intro"] = intro_match.group(1).strip()
                logger.info(f"Parsed intro: {len(parsed_data['intro'])} characters")
            
            contents_match = re.search(r'<contents>(.*?)</contents>', response, re.DOTALL)
            if contents_match:
                # 연속된 줄바꿈을 하나로 변환
                contents = contents_match.group(1).strip()
                contents = re.sub(r'\n{2,}', '\n', contents)
                parsed_data["contents"] = contents
                logger.info(f"Parsed contents: {len(parsed_data['contents'])} characters")
            
            department_match = re.search(r'<department>(.*?)</department>', response, re.DOTALL)
            if department_match:
                parsed_data["department"] = department_match.group(1).strip()
                logger.info(f"Parsed department: {parsed_data['department']}")
            
            # 태그가 없는 경우 전체 응답을 contents로 사용
            if not any(parsed_data.values()):
                logger.info("No tags found, using full response as contents")
                # 연속된 줄바꿈을 하나로 변환
                contents = response.strip()
                contents = re.sub(r'\n{2,}', '\n', contents)
                parsed_data["contents"] = contents
            
            return parsed_data
            
        except Exception as e:
            logger.error(f"Error parsing agent response: {e}", exc_info=True)
            # 오류 발생 시 전체 응답을 contents로 처리
            # 연속된 줄바꿈을 하나로 변환
            contents = response.strip()
            contents = re.sub(r'\n{2,}', '\n', contents)
            return {
                "intro": "",
                "contents": contents,
                "department": ""
            }

    @staticmethod
    def create_slack_blocks(parsed_data: dict) -> List[dict]:
        """
        파싱된 데이터를 Slack Block Kit 형식으로 변환
        
        Args:
            parsed_data: parse_agent_response에서 반환된 데이터
            
        Returns:
            List[dict]: Slack Block Kit 블록 목록
        """
        logger.info("Creating Slack blocks from parsed data")
        blocks = []
        
        # Intro 섹션
        if parsed_data.get("intro"):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": parsed_data["intro"]
                }
            })
            
            blocks.append({"type": "divider"})
        
        # Contents 섹션
        if parsed_data.get("contents"):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": parsed_data["contents"]
                }
            })
        
        # Department 섹션 (버튼)
        if parsed_data.get("department"):
            blocks.append({"type": "divider"})
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*담당 부서 정보*"
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": f"📞 {parsed_data['department']} 정보",
                        "emoji": True
                    },
                    "value": f"department_{parsed_data['department']}",
                    "action_id": "show_department"
                }
            })
        
        logger.info(f"Created {len(blocks)} Slack blocks")
        return blocks
    
    @staticmethod
    def create_department_view(department_name: str) -> List[dict]:
        """
        부서 정보 화면을 위한 Slack 블록 생성
        
        Args:
            department_name: 부서 이름
            
        Returns:
            List[dict]: 부서 정보 화면 블록
        """
        logger.info(f"Creating department view for: {department_name}")
        
        # 부서 정보 가져오기
        dept_info = DEPARTMENT_INFO.get(department_name, {})
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{department_name} 정보* 📞"
                }
            },
            {
                "type": "divider"
            }
        ]
        
        # 부서 설명 추가
        if dept_info.get("description"):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*업무 내용*\n{dept_info.get('description', '정보가 없습니다.')}"
                }
            })
        
        # 연락처 정보 추가
        contact_text = "*연락처 정보*\n"
        if dept_info.get("phone"):
            contact_text += f"📞 전화: {dept_info.get('phone')}\n"
        if dept_info.get("fax"):
            contact_text += f"📠 팩스: {dept_info.get('fax')}\n"
        if dept_info.get("location"):
            contact_text += f"📍 위치: {dept_info.get('location')}\n"
        if dept_info.get("hours"):
            contact_text += f"🕒 운영시간: {dept_info.get('hours')}\n"
            
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": contact_text
            }
        })
        
        # 돌아가기 버튼 추가
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "◀️ 이전으로 돌아가기",
                        "emoji": True
                    },
                    "action_id": "back_to_original"
                }
            ]
        })
        
        logger.info(f"Created {len(blocks)} blocks for department view")
        return blocks
        
    @staticmethod
    def get_plain_text_fallback(parsed_data: dict) -> str:
        """
        파싱된 데이터에서 일반 텍스트 버전 생성 (블록 지원 안 될 때 대체용)
        
        Args:
            parsed_data: 파싱된 데이터
            
        Returns:
            str: 일반 텍스트 메시지
        """
        text_parts = []
        
        if parsed_data.get("intro"):
            text_parts.append(parsed_data["intro"])
            
        if parsed_data.get("contents"):
            text_parts.append(parsed_data["contents"])
            
        if parsed_data.get("department"):
            text_parts.append(f"담당 부서: {parsed_data['department']}")
        
        # 빈 결과가 나올 경우 기본 메시지 제공
        result = "\n".join(text_parts) if text_parts else "죄송합니다. 응답 내용이 없습니다."
        
        logger.info(f"Plain text fallback generated: {len(result)} characters")
        return result
    
    # === Slack 메시지 처리 메서드 추가 ===
    
    def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        thread_ts: Optional[str] = None,
        blocks: Optional[List[dict]] = None
    ) -> Dict[str, Any]:
        """
        Slack 메시지 업데이트
        
        Args:
            channel: 채널 ID
            ts: 메시지 타임스탬프
            text: 업데이트할 텍스트
            thread_ts: 스레드 타임스탬프 (선택사항)
            blocks: 메시지 블록 (선택사항)
            
        Returns:
            dict: Slack API 응답
        """
        if not self.slack_client:
            logger.error("Slack client is not provided")
            raise ValueError("Slack client is required for message updates")
        
        try:
            logger.info(f"Updating message in channel {channel}, ts={ts}")
            
            update_params = {
                "channel": channel,
                "ts": ts,
                "text": text
            }
            
            # 스레드인 경우 thread_ts 추가
            if thread_ts:
                update_params["thread_ts"] = thread_ts
                
            # 블록이 있는 경우 추가
            if blocks:
                update_params["blocks"] = blocks
            
            response = self.slack_client.chat_update(**update_params)
            
            if response["ok"]:
                logger.info("Message updated successfully")
            else:
                logger.error(f"Message update failed: {response.get('error', 'Unknown error')}")
            
            return response
            
        except SlackApiError as e:
            logger.error(f"Slack API error updating message: {e.response['error']}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error updating message: {e}", exc_info=True)
            raise
    
    def post_message(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
        blocks: Optional[List[dict]] = None
    ) -> Dict[str, Any]:
        """
        Slack 메시지 전송
        
        Args:
            channel: 채널 ID
            text: 메시지 텍스트
            thread_ts: 스레드 타임스탬프 (선택사항)
            blocks: 메시지 블록 (선택사항)
            
        Returns:
            dict: Slack API 응답
        """
        if not self.slack_client:
            logger.error("Slack client is not provided")
            raise ValueError("Slack client is required for posting messages")
        
        try:
            logger.info(f"Posting message to channel {channel}")
            
            post_params = {
                "channel": channel,
                "text": text
            }
            
            if thread_ts:
                post_params["thread_ts"] = thread_ts
            
            if blocks:
                post_params["blocks"] = blocks
            
            response = self.slack_client.chat_postMessage(**post_params)
            
            if response["ok"]:
                logger.info(f"Message posted successfully, ts={response['ts']}")
            else:
                logger.error(f"Message post failed: {response.get('error', 'Unknown error')}")
            
            return response
            
        except SlackApiError as e:
            logger.error(f"Slack API error posting message: {e.response['error']}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error posting message: {e}", exc_info=True)
            raise
    
    def post_thinking_message(
        self,
        channel: str,
        thread_ts: Optional[str] = None
    ) -> Optional[str]:
        """
        '생각 중...' 임시 메시지 전송
        
        Args:
            channel: 채널 ID
            thread_ts: 스레드 타임스탬프 (선택사항)
            
        Returns:
            str: 메시지 타임스탬프 (업데이트용)
        """
        try:
            thinking_text = "🤔 생각 중..."
            response = self.post_message(
                channel=channel,
                text=thinking_text,
                thread_ts=thread_ts
            )
            
            if response["ok"]:
                return response["ts"]
            else:
                logger.warning("Failed to post thinking message")
                return None
                
        except Exception as e:
            logger.error(f"Error posting thinking message: {e}")
            return None