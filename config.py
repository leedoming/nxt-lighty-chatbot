import os
import logging

logger = logging.getLogger()

class Config:
    """환경 변수에서 로드되는 설정"""
    # AWS 및 기본 설정
    AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
    SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
    SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
    DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "cindy-gwangju-chat-bot-context")
    
    # 채널 및 메시지 설정
    ALLOWED_CHANNEL_IDS = os.environ.get("ALLOWED_CHANNEL_IDS", "None")
    ALLOWED_CHANNEL_MESSAGE = os.environ.get(
        "ALLOWED_CHANNEL_MESSAGE", "Sorry, I'm not allowed to respond in this channel."
    )
    PERSONAL_MESSAGE = os.environ.get(
        "PERSONAL_MESSAGE", "You are a friendly and professional AI assistant."
    )
    SYSTEM_MESSAGE = os.environ.get("SYSTEM_MESSAGE", "None")
    
    # 메시지 길이 제한
    MAX_LEN_SLACK = int(os.environ.get("MAX_LEN_SLACK", "2000"))
    MAX_LEN_BEDROCK = int(os.environ.get("MAX_LEN_BEDROCK", "4000"))
    MAX_THROTTLE_COUNT = int(os.environ.get("MAX_THROTTLE_COUNT", "100"))
    BOT_CURSOR = os.environ.get("BOT_CURSOR", ":robot_face:")
    
    # Bedrock 설정
    BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    
    # Agent 설정
    AGENT_ID = os.environ.get("AGENT_ID", "MLARXNITGT")
    AGENT_ALIAS_ID = os.environ.get("AGENT_ALIAS_ID", "14GIZ06BOA")
    USE_AGENT = os.environ.get("USE_AGENT", "true").lower() == "true"
    
    # 기능 활성화 설정
    USE_DYNAMODB = os.environ.get("USE_DYNAMODB", "true").lower() == "true"
    USE_BEDROCK = os.environ.get("USE_BEDROCK", "true").lower() == "true"
    
    # 테스트 및 기타 설정
    TEST_RESPONSE = os.environ.get("TEST_RESPONSE", "안녕하세요! 슬랙봇 테스트 중입니다. 이것은 고정된 응답입니다.")
    EVENT_DEDUP_TTL = int(os.environ.get("EVENT_DEDUP_TTL", "600"))
    SLACK_SAY_INTERVAL = float(os.environ.get("SLACK_SAY_INTERVAL", "0"))
    
    # 상태 메시지
    STATUS_PREVIOUS = f"이전 대화 내용 확인 중... {BOT_CURSOR}"
    STATUS_RESPONSE = f"응답 기다리는 중... {BOT_CURSOR}"
    STATUS_ERROR = f"오류가 발생했습니다. 잠시 후 다시 시도해주세요. {BOT_CURSOR}"

    @classmethod
    def validate(cls) -> bool:
        """필수 설정 검증 및 모든 설정 로깅"""
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