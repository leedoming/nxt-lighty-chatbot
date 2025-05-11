# response_parser.py
import re
import logging
import json
import os
from typing import Dict, List, Optional, Any
from slack_bolt import App

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
app = App(token=SLACK_BOT_TOKEN)
# 로거 설정
logger = logging.getLogger()

DEPARTMENT_INFO = {
    "대표전화": {
        "description": "광주대학교 대표 연락처입니다.",
        "phone": "062-670-2114",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "입학처(입학관련)": {
        "description": "신입생 모집 기본계획 수립 및 실행, 입학전형 개발 및 관리, 입학홍보 프로그램 운영, 입시상담 및 민원 처리, 합격자 발표 및 등록 관리, 편입학 전형 관리 등을 담당합니다.",
        "phone": "080-670-2600",
        "fax": "062-670-2626",
        "location": "",
        "hours": ""
    },
    "교무처(수업관련)": {
        "description": "학사일정 수립 및 관리, 교원 인사 및 업적평가 관리, 수업 운영 및 관리(강의계획서, 수업평가, 휴보강 등), 교육과정 개발 및 개편 등을 담당합니다.",
        "phone": "062-670-2108",
        "fax": "062-670-2828",
        "location": "",
        "hours": ""
    },
    "교무처(학적관련)": {
        "description": "학적관리(입학, 졸업, 휴복학, 전과 등), 학위수여 및 졸업 관리, 성적관리 및 학사경고, 교직과정 운영, 현장실습 지원 등을 담당합니다.",
        "phone": "062-670-2737",
        "fax": "062-670-2158",
        "location": "",
        "hours": ""
    },
    "학생지원처(장학관련)": {
        "description": "교내외 장학금 제도 운영, 장학생 선발 및 장학금 지급 관리, 학자금 대출 관련 업무 등을 담당합니다.",
        "phone": "062-670-2516",
        "fax": "062-670-2627",
        "location": "",
        "hours": ""
    },
    "학생지원처(취업관련)": {
        "description": "취업지원 프로그램 운영, 진로 상담 및 취업 정보 제공, 학생회 및 동아리 활동 지원 등을 담당합니다.",
        "phone": "062-670-2910",
        "fax": "062-670-2169",
        "location": "",
        "hours": ""
    },
    "총무처(시설관련)": {
        "description": "시설 및 자산 관리, 교내 시설물 유지보수, 안전관리 등을 담당합니다.",
        "phone": "062-670-2682",
        "fax": "062-670-2145",
        "location": "",
        "hours": ""
    },
    "장애학생지원센터": {
        "description": "장애학생 지원 서비스를 담당합니다.",
        "phone": "062-670-2199",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "건강상담센터": {
        "description": "학생 건강 상담 지원을 담당합니다.",
        "phone": "062-670-2119",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "대학생활·진로상담센터": {
        "description": "생활 및 진로 상담을 담당합니다.",
        "phone": "062-670-2887",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "인권상담실": {
        "description": "인권 상담을 담당합니다.",
        "phone": "062-670-2199",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "성희롱·성폭력상담실": {
        "description": "성희롱 및 성폭력 상담을 담당합니다.",
        "phone": "062-670-2138",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "기획처": {
        "description": "대학 중장기 발전계획 수립, 대학 평가 및 감사 업무, 대학혁신사업 운영, 예산 편성 및 관리, 대학 구조개혁 관련 업무 등을 담당합니다.",
        "phone": "062-670-2785",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "교육혁신처(IR센터)": {
        "description": "교육성과 분석 및 IR 기능을 담당합니다.",
        "phone": "062-670-2144",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "교육혁신처(전공교육센터)": {
        "description": "전공교육 질 관리를 담당합니다.",
        "phone": "062-670-2180",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "교육혁신처(교양교육센터)": {
        "description": "교양교육 질 관리를 담당합니다.",
        "phone": "062-670-2178",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "교육혁신처(교수학생역량센터)": {
        "description": "교수·학습 역량 강화 프로그램 운영을 담당합니다.",
        "phone": "062-670-2190",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "교육혁신처(원격교육센터)": {
        "description": "원격교육 지원을 담당합니다.",
        "phone": "062-670-2183",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "국제협력처(중국)": {
        "description": "중국 관련 국제 교류 협정 체결 및 관리, 유학생 유치 및 관리 등을 담당합니다.",
        "phone": "062-670-2858",
        "fax": "062-670-2733",
        "location": "",
        "hours": ""
    },
    "국제협력처(베트남)": {
        "description": "베트남 관련 국제 교류 협정 체결 및 관리, 유학생 유치 및 관리 등을 담당합니다.",
        "phone": "062-670-2779",
        "fax": "062-670-2733",
        "location": "",
        "hours": ""
    },
    "국제협력처(몽골 및 기타국가)": {
        "description": "몽골 및 기타국가 관련 국제 교류 협정 체결 및 관리, 유학생 유치 및 관리 등을 담당합니다.",
        "phone": "062-670-2569",
        "fax": "062-670-2733",
        "location": "",
        "hours": ""
    },
    "총무팀": {
        "description": "직원 인사 및 복무 관리, 교직원 연금, 보험 등 관련 업무를 담당합니다.",
        "phone": "062-670-2584",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "재무회계팀": {
        "description": "재무회계 관리, 등록금 수납 및 관리를 담당합니다.",
        "phone": "062-670-2583",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "시설관리팀": {
        "description": "시설 및 자산 관리, 교내 시설물 유지보수를 담당합니다.",
        "phone": "062-670-2577",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "중대재해예방팀": {
        "description": "안전관리(연구실 안전, 산업안전, 소방안전 등)를 담당합니다.",
        "phone": "062-670-2575",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "대외협력처(홍보팀)": {
        "description": "대학 홍보 및 이미지 제고, 대학 소식 및 언론 보도 관리, 홍보물 제작 및 배포를 담당합니다.",
        "phone": "062-670-2236",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "대외협력처(소통협력팀)": {
        "description": "지역사회 협력 프로그램 운영을 담당합니다.",
        "phone": "062-670-2151",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "대외협력처(미디어센터)": {
        "description": "대학 미디어 관련 업무를 담당합니다.",
        "phone": "062-670-2415",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "호심취·창업지원단(대학일자리플러스센터)": {
        "description": "진로, 취·창업 지원 기본계획 수립, 진로, 취·창업 상담 운영 관리, 진로, 취·창업 프로그램 기획 및 운영 등을 담당합니다.",
        "phone": "062-670-2911",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "산학협력단(창업보육센터)": {
        "description": "창업보육센터 운영을 담당합니다.",
        "phone": "062-670-2699",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "산학협력단(지역사회협력센터)": {
        "description": "지역사회 협력 사업 수행을 담당합니다.",
        "phone": "062-670-2392",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "산학협력단(공용장비지원센터)": {
        "description": "공용장비 지원을 담당합니다.",
        "phone": "062-670-2030",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "정보전산원(수강/성적/시간강사/학적)": {
        "description": "정보화 정책, 전산자원, 서버 관리, 프로그램 개발 등의 업무 중 수강, 성적, 시간강사, 학적 관련 업무를 담당합니다.",
        "phone": "062-670-2251",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "정보전산원(입시/교직원채용)": {
        "description": "정보화 정책, 전산자원, 서버 관리, 프로그램 개발 등의 업무 중 입시, 교직원채용 관련 업무를 담당합니다.",
        "phone": "062-670-2132",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "정보전산원(등록/장학)": {
        "description": "정보화 정책, 전산자원, 서버 관리, 프로그램 개발 등의 업무 중 등록, 장학 관련 업무를 담당합니다.",
        "phone": "062-670-2131",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "정보전산원(급여/연말정산/기자재/생활관)": {
        "description": "정보화 정책, 전산자원, 서버 관리, 프로그램 개발 등의 업무 중 급여, 연말정산, 기자재, 생활관 관련 업무를 담당합니다.",
        "phone": "062-670-2871",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "정보전산원(대학원)": {
        "description": "정보화 정책, 전산자원, 서버 관리, 프로그램 개발 등의 업무 중 대학원 관련 업무를 담당합니다.",
        "phone": "062-670-2875",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "정보전산원(네트워크/이메일/백신)": {
        "description": "정보화 정책, 전산자원, 서버 관리, 프로그램 개발 등의 업무 중 네트워크, 이메일, 백신 관련 업무를 담당합니다.",
        "phone": "062-670-2884",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "정보전산원(PC고장신고)": {
        "description": "PC고장신고 업무를 담당합니다.",
        "phone": "062-670-2602",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "호심기념도서관": {
        "description": "자료의 선정 및 구입, 기증·수증 관련 업무, 자료의 등록 및 제적, 자료의 분류 및 정리 등의 도서관 관련 업무를 담당합니다.",
        "phone": "062-670-2385",
        "fax": "062-670-2630",
        "location": "",
        "hours": ""
    },
    "평생교육원": {
        "description": "평생교육 프로그램 개발 및 운영, 학점은행제 과정 운영, 자격증 과정 운영, 지역사회 교육 프로그램 운영 등을 담당합니다.",
        "phone": "062-670-2167",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "생활관(매원관-남자)": {
        "description": "생활관 운영계획 수립, 관리비 책정, 사생 모집 및 선발, 생활 지도 및 상담 등을 담당합니다.",
        "phone": "062-670-2802",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "생활관(사임당관-여자)": {
        "description": "생활관 운영계획 수립, 관리비 책정, 사생 모집 및 선발, 생활 지도 및 상담 등을 담당합니다.",
        "phone": "062-670-2813",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "학생군사교육단": {
        "description": "학생군사교육 관련 업무를 담당합니다.",
        "phone": "062-670-2205",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "예비군대대": {
        "description": "예비군 관련 업무를 담당합니다.",
        "phone": "062-670-2161",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "체육관": {
        "description": "체육관 관련 업무를 담당합니다.",
        "phone": "062-670-2311",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "호심미술관": {
        "description": "미술관 관련 업무를 담당합니다.",
        "phone": "062-670-2173",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "남구어린이급식관리지원센터": {
        "description": "어린이급식 관리 지원 업무를 담당합니다.",
        "phone": "062-670-2974",
        "fax": "",
        "location": "",
        "hours": ""
    },
    "남구사회복지급식관리지원센터": {
        "description": "사회복지급식 관리 지원 업무를 담당합니다.",
        "phone": "062-670-2314",
        "fax": "",
        "location": "",
        "hours": ""
    }
}

class ResponseParser:
    """Bedrock Agent 응답을 파싱하고 Slack 메시지 형태로 변환하는 클래스"""
    
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
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{department_name} 정보*"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{department_name}에 대한 기본 정보입니다.\n\n담당 부서: {department_name}\n연락처: 062-000-0000"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "◀️ 돌아가기",
                            "emoji": True
                        },
                        "action_id": "back_to_original"
                    }
                ]
            }
        ]
        
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
    
# 이벤트 핸들러 추가

# 테스트용 버튼 핸들러 (가장 기본 형태)

@app.action("show_department")
# This code should be added to the main Lambda function file

def handle_show_department(ack, body, client):
    """Handle the department information button click"""
    # Always acknowledge the action first
    ack()
    
    try:
        logger.info("Handling department button click")
        
        # Extract department name from button value
        action = body["actions"][0]
        department_value = action["value"]
        department_name = department_value.replace("department_", "")
        
        # Get message details
        channel_id = body["channel"]["id"]
        message_ts = body["message"]["ts"]
        user_id = body["user"]["id"]
        
        # Create key for storing original message
        message_key = f"original_{message_ts}"
        
        # Retrieve the current blocks before overwriting
        try:
            current_blocks = body["message"]["blocks"]
            current_text = body["message"]["text"]
            
            # Store the original message data if it doesn't exist yet
            if Config.USE_DYNAMODB and DynamoDBManager.get_context(message_key, user_id) == "":
                logger.info(f"Storing original message for key={message_key}")
                original_data = {
                    "blocks": current_blocks,
                    "text": current_text,
                    "department": department_name
                }
                DynamoDBManager.put_context(
                    message_key, 
                    user_id, 
                    json.dumps(original_data)
                )
                logger.info(f"Original message stored successfully")
        except Exception as store_err:
            logger.error(f"Error storing original message: {store_err}", exc_info=True)
        
        # Look up department information
        dept_info = DEPARTMENT_INFO.get(department_name, {})
        
        # Create department view blocks
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
        
        # Add department description if available
        if dept_info.get("description"):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*업무 내용*\n{dept_info.get('description', '정보가 없습니다.')}"
                }
            })
        
        # Add contact information section
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
        
        # Add back button
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
        
        # Update the message
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            blocks=blocks,
            text=f"{department_name} 부서 정보"
        )
        
        logger.info(f"Department view displayed for {department_name}")
        
    except Exception as e:
        logger.error(f"Error handling department button: {e}", exc_info=True)
        # Send an ephemeral message to notify the user of the error
        try:
            client.chat_postEphemeral(
                channel=body["channel"]["id"],
                user=body["user"]["id"],
                text="부서 정보를 표시하는 중 오류가 발생했습니다."
            )
        except:
            pass

def handle_back_to_original(ack, body, client):
    """Handle the back button click"""
    # Always acknowledge the action first
    ack()
    
    try:
        logger.info("Handling back button click")
        
        # Get message details
        channel_id = body["channel"]["id"]
        message_ts = body["message"]["ts"]
        user_id = body["user"]["id"]
        
        # Create key for retrieving original message
        message_key = f"original_{message_ts}"
        
        # Retrieve original message from DynamoDB
        if Config.USE_DYNAMODB:
            original_data_str = DynamoDBManager.get_context(message_key, user_id)
            
            if original_data_str:
                try:
                    # Parse the JSON data
                    original_data = json.loads(original_data_str)
                    
                    # Update message with original blocks and text
                    client.chat_update(
                        channel=channel_id,
                        ts=message_ts,
                        blocks=original_data.get("blocks", []),
                        text=original_data.get("text", "원본 메시지")
                    )
                    
                    logger.info("Successfully restored original message")
                    return
                except json.JSONDecodeError as json_err:
                    logger.error(f"Error parsing original message data: {json_err}", exc_info=True)
            else:
                logger.warning(f"No original message found for key={message_key}")
        
        # Fallback if original message not found or DynamoDB disabled
        fallback_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*원본 메시지를 찾을 수 없습니다* 🔍\n\n이전 메시지 정보를 복원할 수 없습니다. 새로운 질문을 입력해주세요."
                }
            }
        ]
        
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            blocks=fallback_blocks,
            text="원본 메시지를 찾을 수 없습니다"
        )
        
        logger.info("Used fallback for back button (original message not found)")
        
    except Exception as e:
        logger.error(f"Error handling back button: {e}", exc_info=True)
        # Send an ephemeral message to notify the user of the error
        try:
            client.chat_postEphemeral(
                channel=body["channel"]["id"],
                user=body["user"]["id"],
                text="이전 화면으로 돌아가는 중 오류가 발생했습니다."
            )
        except:
            pass

# Register the handlers with the Bolt app
app.action("show_department")(handle_show_department)
app.action("back_to_original")(handle_back_to_original)
