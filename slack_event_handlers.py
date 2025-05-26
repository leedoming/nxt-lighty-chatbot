# slack_event_handlers.py
"""
Slack 이벤트 처리 핸들러 모듈
"""
import logging
import re
import json

from config import Config
from conversation_handler import conversation, is_duplicate_event

logger = logging.getLogger()

def register_event_handlers(app, bot_id=None):
    """
    Slack 이벤트 핸들러 등록
    
    Args:
        app: Slack App 인스턴스
        bot_id: 봇 ID (멘션 처리용)
    """

    @app.event("app_mention")
    def handle_app_mention_events(body, say, logger):
        """앱 멘션 이벤트 처리 (채널에서 봇을 멘션한 경우)"""
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

            # 허용된 채널인지 확인
            if Config.ALLOWED_CHANNEL_IDS != "None":
                logger.info(f"Checking if channel {channel} is in allowed channels: {Config.ALLOWED_CHANNEL_IDS}")
                allowed_channel_ids = Config.ALLOWED_CHANNEL_IDS.split(",")
                if channel not in allowed_channel_ids:
                    first_channel = f"<#{allowed_channel_ids[0]}>"
                    message = Config.ALLOWED_CHANNEL_MESSAGE.format(first_channel)
                    logger.info(f"Channel {channel} not allowed, sending message: {message}")
                    say(text=message, thread_ts=thread_ts)
                    return

            # 쿼리 텍스트 추출 (봇 멘션 제거)
            if bot_id:
                prompt = re.sub(f"<@{bot_id}>", "", event["text"]).strip()
            else:
                # Bot ID를 구하지 못한 경우 전체 텍스트 사용
                prompt = event["text"].strip()
            logger.info(f"Extracted prompt: '{prompt}'")
            
            # 대화 처리
            conversation(app, say, prompt, thread_ts, channel, client_msg_id, user)
        except Exception as e:
            logger.error(f"Error in handle_mention: {e}", exc_info=True)
            
            # 마지막 시도 - 직접 에러 메시지 보내기
            try:
                if 'channel' in locals() and 'thread_ts' in locals():
                    say(text=f"오류가 발생했습니다. 관리자에게 문의하세요. 오류 정보: {str(e)[:100]}", thread_ts=thread_ts)
            except:
                pass  # 정말 최후의 시도도 실패하면 포기


    @app.event("message")
    def handle_message(body, say, logger):
        """DM 메시지 이벤트 처리 (봇에게 직접 메시지를 보낸 경우)"""
        logger.info(f"Received message event: {json.dumps(body)[:500]}...")

        # 중복 이벤트 확인 (중요: 최우선으로 확인)
        if is_duplicate_event(body):
            logger.info("중복된, 이미 처리된 메시지 이벤트이므로 무시합니다.")
            return

        try:
            event = body["event"]

            # 봇의 메시지 무시 (이 봇 포함)
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
            logger.info(f"Processing DM from user {user} in channel {channel}: '{prompt}'")

            # 대화 처리 (DM의 경우 thread_ts=None)
            conversation(app, say, prompt, None, channel, client_msg_id, user)
            
        except Exception as e:
            logger.error(f"Error in handle_message: {e}", exc_info=True)
            
            # 마지막 시도 - 직접 에러 메시지 보내기
            try:
                if 'channel' in locals():
                    say(text=f"DM 처리 중 오류가 발생했습니다. 관리자에게 문의하세요. 오류 정보: {str(e)[:100]}")
            except:
                pass  # 정말 최후의 시도도 실패하면 포기

    # 모든 이벤트 로깅을 위한 미들웨어 추가
    @app.middleware
    def log_all_requests(payload, next):
        """모든 요청을 로깅하는 미들웨어"""
        try:
            logger.info(f"[미들웨어] 수신된 페이로드 타입: {payload.get('type', '알 수 없음')}")
            
            # 액션 이벤트인 경우 더 자세히 로깅
            if payload.get("type") == "block_actions":
                logger.info(f"[미들웨어] 액션 감지됨!")
                logger.info(f"[미들웨어] 액션 ID: {payload.get('actions', [{}])[0].get('action_id', '알 수 없음')}")
                logger.info(f"[미들웨어] 사용자: {payload.get('user', {}).get('id', '알 수 없음')}")
        except Exception as e:
            logger.error(f"[미들웨어] 로깅 중 오류: {e}")
        
        # 다음 핸들러로 진행
        return next()

    logger.info("Slack event handlers registered successfully")