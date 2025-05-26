# aws_clients.py
"""
AWS 서비스 클라이언트 초기화 모듈
"""
import boto3
import logging
import time
import json
from datetime import datetime
from boto3.dynamodb.conditions import Key
from typing import Optional

from config import Config

logger = logging.getLogger()

# AWS 클라이언트 초기화
dynamodb = None
table = None
bedrock_runtime = None
bedrock_agent_runtime = None

def initialize_aws_clients():
    """AWS 클라이언트 초기화"""
    global dynamodb, table, bedrock_runtime, bedrock_agent_runtime
    
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
            
            # AFTER initialization, check if clients were created successfully
            if bedrock_agent_runtime is None:
                logger.error("bedrock_agent_runtime is None after initialization!")
            else:
                logger.info("bedrock_agent_runtime successfully initialized.")
                
                # Optional: Test the client with a simple operation
                try:
                    # Test if the client can access the service
                    # This doesn't make an actual API call, just validates the client setup
                    logger.info(f"Bedrock Agent Runtime endpoint: {bedrock_agent_runtime._endpoint.host}")
                    logger.info(f"Bedrock Agent Runtime region: {bedrock_agent_runtime._client_config.region_name}")
                except Exception as test_error:
                    logger.warning(f"Client test failed, but client exists: {test_error}")
                    
        except Exception as e:
            logger.error(f"Error initializing Bedrock clients: {e}", exc_info=True)
            logger.warning("Bedrock initialization failed, will continue with test responses")
            # Set clients to None to ensure they're not in an undefined state
            bedrock_runtime = None
            bedrock_agent_runtime = None
    else:
        logger.info("Bedrock is disabled by configuration")


class DynamoDBManager:
    """DynamoDB 작업 관리 클래스"""

    @staticmethod
    def get_context(thread_ts: Optional[str], user: str, default: str = "") -> str:
        """DynamoDB에서 대화 컨텍스트 조회"""
        # DynamoDB를 사용하지 않으면 기본값 반환
        if not Config.USE_DYNAMODB or table is None:
            logger.info("DynamoDB disabled or not initialized, returning default context")
            return default
            
        try:
            logger.info(f"Getting context from DynamoDB for thread_ts={thread_ts}, user={user}")
            key = {"id": thread_ts if thread_ts else user}
            response = table.get_item(Key=key)
            
            logger.info("DynamoDB get_item response received")
            
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
        """DynamoDB에 대화 컨텍스트 저장 (TTL 포함)"""
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
        """특정 사용자에 속한 컨텍스트 수 조회"""
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

__all__ = ['bedrock_runtime', 'bedrock_agent_runtime', 'initialize_aws_clients', 'DynamoDBManager']