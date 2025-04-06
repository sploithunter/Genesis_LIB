"""
OpenAI chat agent implementation for the GENESIS library
"""

import logging
import os
import json
from typing import Optional, Dict, Any, List, Tuple
from openai import OpenAI
from .llm import ChatAgent, Message

class OpenAIChatAgent(ChatAgent):
    """Chat agent using OpenAI models"""
    def __init__(self, model_name: str = "gpt-3.5-turbo", api_key: Optional[str] = None,
                 system_prompt: Optional[str] = None, max_history: int = 10):
        super().__init__("OpenAI", model_name, system_prompt, max_history)
        # Get API key from environment if not provided
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key is None:
                raise ValueError("OPENAI_API_KEY environment variable is not set")
        self.client = OpenAI(api_key=api_key)
        self.logger.info(f"OpenAIChatAgent initialized with model {model_name}")
    
    def generate_response(self, message: str, conversation_id: str) -> Tuple[str, int]:
        """Generate a response using OpenAI without function calling"""
        try:
            self.logger.info(f"OpenAIChatAgent.generate_response called with message: '{message[:30]}...'")
            
            # Get or create conversation history
            if conversation_id not in self.conversations:
                self.conversations[conversation_id] = []
            
            # Add user message
            self.conversations[conversation_id].append(
                Message(role="user", content=message)
            )
            
            # Clean up empty messages from conversation history
            self.conversations[conversation_id] = [
                msg for msg in self.conversations[conversation_id]
                if msg.content.strip()  # Keep only messages with non-empty content
            ]
            
            # Generate response
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt if self.system_prompt else "You are a helpful AI assistant."},
                    *[{"role": msg.role, "content": msg.content} for msg in self.conversations[conversation_id]]
                ]
            )
            
            # Get response text
            response_text = response.choices[0].message.content
            
            # Add assistant response only if it's not empty
            if response_text.strip():
                self.conversations[conversation_id].append(
                    Message(role="assistant", content=response_text)
                )
            
            # Cleanup old conversations
            self._cleanup_old_conversations()
            
            return response_text, 0
            
        except Exception as e:
            self.logger.error(f"Error generating response: {e}")
            return str(e), 1 