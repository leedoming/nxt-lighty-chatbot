# bedrock_manager.py
"""
Amazon Bedrock 서비스 호출 및 응답 처리
"""
import json
import time
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from config import Config
import aws_clients  # 모듈 자체를 import

logger = logging.getLogger()

class BedrockManager:
    """Amazon Bedrock 작업 처리"""

    @staticmethod
    def invoke_model(prompt: str) -> str:
        """
        Amazon Bedrock 모델 호출하고 응답 반환
        
        Args:
            prompt: 모델에 전달할 프롬프트
            
        Returns:
            str: 모델 응답
        """
        # aws_clients 모듈에서 동적으로 가져오기
        bedrock_runtime = getattr(aws_clients, 'bedrock_runtime', None)
        
        if not Config.USE_BEDROCK or bedrock_runtime is None:
            logger.info("Bedrock disabled or not initialized, returning test response")
            return f"{Config.TEST_RESPONSE}\n\n요청하신 쿼리: '{prompt[:100]}'"
        
        try:
            logger.info(f"Invoking Bedrock model: {Config.BEDROCK_MODEL_ID}")
            logger.info(f"Prompt length: {len(prompt)} characters")
            
            # Anthropic Claude 모델 요청 형식
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            # Bedrock 모델 호출
            start_time = time.time()
            response = bedrock_runtime.invoke_model(
                modelId=Config.BEDROCK_MODEL_ID,
                body=json.dumps(request_body)
            )
            end_time = time.time()
            
            logger.info(f"Model response received in {end_time - start_time:.2f}s")
            
            # 응답 처리
            response_body = json.loads(response.get("body").read())
            logger.info(f"Bedrock response received: {len(str(response_body))} bytes")
            
            if "content" in response_body and len(response_body.get("content", [])) > 0:
                content = response_body.get("content", [])[0].get("text", "")
                logger.info(f"Response preview: {content[:200]}...")
                return content
            else:
                logger.error(f"Unexpected response format from Bedrock: {response_body}")
                return "죄송합니다. 응답을 처리하는 중 오류가 발생했습니다."
            
        except Exception as e:
            logger.error(f"Error invoking Bedrock model: {e}", exc_info=True)
            
            # 상세한 오류 정보 로깅
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "model_id": Config.BEDROCK_MODEL_ID,
                "bedrock_runtime_available": bedrock_runtime is not None
            }
            logger.error(f"Error details: {error_details}")
            
            # 구체적인 오류 메시지 제공
            if "ValidationException" in str(e):
                return "모델 설정에 문제가 있습니다. 관리자에게 문의해주세요."
            elif "AccessDeniedException" in str(e):
                return "Bedrock 서비스 권한이 없습니다. 관리자에게 문의해주세요."
            elif "ModelNotReadyException" in str(e):
                return "AI 모델이 준비되지 않았습니다. 잠시 후 다시 시도해주세요."
            elif "ThrottlingException" in str(e):
                return "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."
            else:
                return f"죄송합니다. 응답을 생성하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요. (오류: {type(e).__name__})"

    @staticmethod
    def invoke_agent(prompt: str) -> str:
        """
        Amazon Bedrock Agent 호출하고 응답 반환
        
        Args:
            prompt: 에이전트에 전달할 프롬프트
            
        Returns:
            str: 에이전트 응답
        """
        # aws_clients 모듈에서 동적으로 가져오기
        bedrock_agent_runtime = getattr(aws_clients, 'bedrock_agent_runtime', None)
        
        if not Config.USE_BEDROCK or bedrock_agent_runtime is None:
            logger.info("Bedrock Agent disabled or not initialized, returning test response")
            return f"{Config.TEST_RESPONSE}\n\n요청하신 쿼리: '{prompt[:100]}'"
        
        # Agent 설정 확인
        if not hasattr(Config, 'AGENT_ID') or not Config.AGENT_ID:
            logger.error("AGENT_ID not configured")
            return "Agent 설정이 누락되었습니다. 관리자에게 문의해주세요."
            
        if not hasattr(Config, 'AGENT_ALIAS_ID') or not Config.AGENT_ALIAS_ID:
            logger.error("AGENT_ALIAS_ID not configured")
            return "Agent 별칭 설정이 누락되었습니다. 관리자에게 문의해주세요."
        
        try:
            # 고유 세션 ID 생성
            now = datetime.now()
            session_id = str(int(now.timestamp() * 1000))
            
            logger.info(f"Invoking Bedrock Agent: {Config.AGENT_ID} with alias: {Config.AGENT_ALIAS_ID}")
            logger.info(f"Session ID: {session_id}")
            logger.info(f"Prompt length: {len(prompt)} characters")
            
            # Bedrock Agent 호출
            start_time = time.time()
            response = bedrock_agent_runtime.invoke_agent(
                agentId=Config.AGENT_ID,
                agentAliasId=Config.AGENT_ALIAS_ID,
                sessionId=session_id,
                inputText=prompt,
            )
            
            # 스트리밍 응답 처리
            completion = ""
            chunk_count = 0
            
            logger.info("Processing streaming response...")
            
            # response.get("completion", [])가 iterator인 경우 처리
            completion_stream = response.get("completion")
            if completion_stream is None:
                logger.error("No completion stream in response")
                return "Agent 응답을 받을 수 없습니다. 다시 시도해주세요."
            
            for event in completion_stream:
                try:
                    chunk = event.get("chunk", {})
                    if chunk and "bytes" in chunk:
                        chunk_data = chunk["bytes"].decode('utf-8')
                        completion += chunk_data
                        chunk_count += 1
                        
                        # 10개 청크마다 또는 첫/마지막 청크에 대해 로깅
                        if chunk_count == 1 or chunk_count % 10 == 0:
                            logger.info(f"Received chunk {chunk_count}, current completion length: {len(completion)}")
                    else:
                        logger.warning(f"Unexpected chunk format: {chunk}")
                        
                except Exception as chunk_error:
                    logger.error(f"Error processing chunk {chunk_count}: {chunk_error}")
                    continue
            
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            logger.info(f"Bedrock Agent response completed in {elapsed_time:.2f}s")
            logger.info(f"Total chunks received: {chunk_count}")
            logger.info(f"Final response length: {len(completion)} characters")
            
            if completion and completion.strip():
                # 응답 미리보기 로깅 (디버깅용)
                logger.info(f"Response preview: {completion[:200]}...")
                return completion.strip()
            else:
                logger.warning("Bedrock Agent returned empty response")
                return "죄송합니다. Agent가 빈 응답을 반환했습니다. 질문을 다시 입력해주세요."

        except Exception as e:
            logger.error(f"Error invoking Bedrock Agent: {e}", exc_info=True)
            
            # 상세한 오류 정보 로깅
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "agent_id": getattr(Config, 'AGENT_ID', 'Not configured'),
                "agent_alias_id": getattr(Config, 'AGENT_ALIAS_ID', 'Not configured'),
                "bedrock_agent_runtime_available": bedrock_agent_runtime is not None
            }
            logger.error(f"Error details: {error_details}")
            
            # 특정 오류 타입에 따른 처리
            if "ThrottlingException" in str(e):
                return "현재 서비스가 혼잡합니다. 잠시 후 다시 시도해주세요."
            elif "ValidationException" in str(e):
                return "Agent 요청 형식에 문제가 있습니다. 관리자에게 문의해주세요."
            elif "ResourceNotFoundException" in str(e):
                return "Agent를 찾을 수 없습니다. 관리자에게 문의해주세요."
            elif "AccessDeniedException" in str(e):
                return "Agent 호출 권한이 없습니다. 관리자에게 문의해주세요."
            elif "TimeoutError" in str(e) or "timeout" in str(e).lower():
                return "응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
            else:
                return f"죄송합니다. Agent 응답을 생성하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요. (오류: {type(e).__name__})"

    @staticmethod
    def create_prompt(query: str, thread_history: Optional[List[str]] = None) -> str:
        """
        AI 모델용 구조화된 프롬프트 생성
        
        Args:
            query: 사용자 쿼리
            thread_history: 대화 이력 (선택사항)
            
        Returns:
            str: 최종 프롬프트
        """
        logger.info(f"Creating prompt for query: {query[:100]}...")
        prompts = []
        
        # 시스템 및 개인화 메시지 추가
        prompts.append("당신은 마스코트 '라이티(Lighty)'입니다. '광주대학교'의 Slack 채팅방에서 활동하는 전문적이고 친근한 광주대 마스코트입니다.")
        prompts.append("따뜻하고, 친근하며, 전문적인 방식으로 이모지를 섞어 메시지에 응답하세요.")
        
        # Config 속성 안전하게 확인
        personal_message = getattr(Config, 'PERSONAL_MESSAGE', '')
        if personal_message:
            prompts.append(f"User: {personal_message}")
        
        system_message = getattr(Config, 'SYSTEM_MESSAGE', 'None')
        if system_message and system_message != "None":
            prompts.append(system_message)
        
        # 태그 기반 지시사항 추가
        prompts.append("")
        
        # 대화 이력 추가
        if thread_history and len(thread_history) > 0:
            logger.info(f"Adding {len(thread_history)} messages from thread history to prompt")
            prompts.append("<history>에 정보가 제공되면, 대화 기록을 참고하여 답변해 주세요.")
            prompts.append("<history>")
            prompts.append("\n\n".join(thread_history))
            prompts.append("</history>")
        
        # 현재 쿼리 추가
        prompts.append("")
        prompts.append("<question>")
        prompts.append(query)
        prompts.append("</question>")
        prompts.append("")
        
        # 응답 시작 표시
        prompts.append("Assistant:")
        
        # 최종 프롬프트 생성
        final_prompt = "\n".join(prompts)
        logger.info(f"Final prompt created: {len(final_prompt)} characters")
        
        return final_prompt

    @staticmethod
    def test_bedrock_connection() -> Dict[str, Any]:
        """
        Bedrock 연결 상태 테스트
        
        Returns:
            dict: 테스트 결과
        """
        result = {
            "bedrock_runtime_available": False,
            "bedrock_agent_runtime_available": False,
            "test_model_call": False,
            "test_agent_call": False,
            "errors": []
        }
        
        try:
            # Runtime 클라이언트 확인
            bedrock_runtime = getattr(aws_clients, 'bedrock_runtime', None)
            result["bedrock_runtime_available"] = bedrock_runtime is not None
            
            # Agent Runtime 클라이언트 확인
            bedrock_agent_runtime = getattr(aws_clients, 'bedrock_agent_runtime', None)
            result["bedrock_agent_runtime_available"] = bedrock_agent_runtime is not None
            
            # 간단한 모델 호출 테스트 (실제 호출하지 않음)
            if bedrock_runtime and hasattr(Config, 'BEDROCK_MODEL_ID') and Config.BEDROCK_MODEL_ID:
                result["test_model_call"] = True
            else:
                result["errors"].append("Bedrock model configuration missing")
            
            # Agent 설정 확인 (실제 호출하지 않음)
            if (bedrock_agent_runtime and 
                hasattr(Config, 'AGENT_ID') and Config.AGENT_ID and
                hasattr(Config, 'AGENT_ALIAS_ID') and Config.AGENT_ALIAS_ID):
                result["test_agent_call"] = True
            else:
                result["errors"].append("Bedrock agent configuration missing")
                
        except Exception as e:
            result["errors"].append(f"Test error: {str(e)}")
            
        return result