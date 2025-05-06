#!/usr/bin/env python3

"""
Genesis Function Classifier

This module provides intelligent function classification capabilities for the Genesis framework,
enabling efficient and accurate matching between user queries and available functions. It serves
as a critical component in the function discovery and selection pipeline, using lightweight LLMs
to quickly identify relevant functions before deeper processing.

Key responsibilities include:
- Rapid classification of functions based on user queries
- Intelligent filtering of irrelevant functions
- Optimization of function selection for LLM processing
- Support for complex function metadata analysis
- Integration with the Genesis function discovery system

The FunctionClassifier enables the Genesis network to efficiently match user needs with
available capabilities, reducing the cognitive load on primary LLMs and improving
response times.

Copyright (c) 2025, RTI & Jason Upchurch
"""

import os
import logging
import json
from typing import Dict, List, Any, Optional

# Configure logging
logger = logging.getLogger("genesis_function_classifier")

class FunctionClassifier:
    """
    Class for classifying and filtering functions based on their relevance to a user query.
    This class uses a lightweight LLM to quickly identify which functions are relevant
    to a given user query, reducing the number of functions that need to be passed to
    the main processing LLM.
    """
    
    def __init__(self, llm_client=None):
        """
        Initialize the function classifier
        
        Args:
            llm_client: The LLM client to use for classification (optional)
        """
        self.llm_client = llm_client
        logger.info("===== TRACING: FunctionClassifier initialized =====")
    
    def _format_for_classification(self, functions: List[Dict]) -> str:
        """
        Format function metadata for efficient classification
        
        Args:
            functions: List of function metadata dictionaries
            
        Returns:
            Formatted function metadata as a string
        """
        formatted_functions = []
        
        for func in functions:
            # Extract the essential information for classification
            name = func.get("name", "")
            description = func.get("description", "")
            
            # Format the function information
            formatted_function = f"Function: {name}\nDescription: {description}\n"
            
            # Add parameter information if available
            schema = func.get("schema", {})
            if schema and "properties" in schema:
                formatted_function += "Parameters:\n"
                for param_name, param_info in schema["properties"].items():
                    param_desc = param_info.get("description", "")
                    formatted_function += f"- {param_name}: {param_desc}\n"
            
            formatted_functions.append(formatted_function)
        
        # Combine all formatted functions into a single string
        return "\n".join(formatted_functions)
    
    def _build_classification_prompt(self, query: str, formatted_functions: str) -> str:
        """
        Build a prompt for the classification LLM
        
        Args:
            query: The user query
            formatted_functions: Formatted function metadata
            
        Returns:
            Classification prompt as a string
        """
        return f"""
You are a function classifier for a distributed system. Your task is to identify which functions are relevant to the user's query.

User Query: {query}

Available Functions:
{formatted_functions}

Instructions:
1. Analyze the user query carefully.
2. Identify which functions would be helpful in answering the query.
3. Return ONLY the names of the relevant functions, one per line.
4. If no functions are relevant, return "NONE".

Relevant Functions:
"""
    
    def _parse_classification_result(self, result: str) -> List[str]:
        """
        Parse the classification result from the LLM
        
        Args:
            result: The classification result from the LLM
            
        Returns:
            List of relevant function names
        """
        # Split the result into lines and clean up
        lines = [line.strip() for line in result.strip().split("\n") if line.strip()]
        
        # Filter out any lines that are not function names
        function_names = []
        for line in lines:
            # Skip lines that are clearly not function names
            if line.lower() == "none":
                return []
            # Skip the "Relevant Functions" header that might be included in the response
            if line.lower() == "relevant functions":
                continue
            if ":" in line or line.startswith("-") or line.startswith("*"):
                # Extract the function name if it's in a list format
                parts = line.split(":", 1)
                if len(parts) > 1:
                    name = parts[0].strip("-* \t")
                    function_names.append(name)
                else:
                    name = line.strip("-* \t")
                    function_names.append(name)
            else:
                function_names.append(line)
        
        return function_names
    
    def classify_functions(self, query: str, functions: List[Dict], model_name: str = "gpt-4o") -> List[Dict]:
        """
        Classify functions based on their relevance to the user query
        
        Args:
            query: The user query
            functions: List of function metadata dictionaries
            model_name: The model to use for classification (default: "gpt-4o")
            
        Returns:
            List of relevant function metadata dictionaries
        """
        logger.info(f"===== TRACING: Classifying functions for query: {query} =====")
        
        # If no LLM client is provided, return all functions
        if not self.llm_client:
            logger.warning("===== TRACING: No LLM client provided, returning all functions =====")
            return functions
        
        # If there are no functions, return an empty list
        if not functions:
            logger.warning("===== TRACING: No functions to classify =====")
            return []
        
        try:
            # Format the functions for classification
            formatted_functions = self._format_for_classification(functions)
            
            # Build the classification prompt
            prompt = self._build_classification_prompt(query, formatted_functions)
            
            # Call the LLM for classification
            logger.info("===== TRACING: Calling LLM for function classification =====")
            
            # Use the OpenAI chat completions API with the specified model
            response = self.llm_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a function classifier that identifies relevant functions for user queries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            # Extract the result from the response
            result = response.choices[0].message.content
            
            # Parse the classification result
            relevant_function_names = self._parse_classification_result(result)
            
            logger.info(f"===== TRACING: Identified {len(relevant_function_names)} relevant functions =====")
            for name in relevant_function_names:
                logger.info(f"===== TRACING: Relevant function: {name} =====")
            
            # Filter the functions based on the classification result
            relevant_functions = []
            for func in functions:
                if func.get("name") in relevant_function_names:
                    relevant_functions.append(func)
            
            return relevant_functions
        except Exception as e:
            logger.error(f"===== TRACING: Error classifying functions: {str(e)} =====")
            # In case of error, return all functions
            return functions 