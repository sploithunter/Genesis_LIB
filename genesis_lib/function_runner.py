"""
Function Runner module for managing Genesis function processes
"""

import os
import sys
import signal
import logging
import threading
import subprocess
from typing import Dict, Optional, List
from pathlib import Path

class FunctionRunner:
    """
    Manages multiple Genesis function processes, handling their lifecycle and output.
    """
    
    def __init__(self, functions_dir: Optional[str] = None):
        """
        Initialize the FunctionRunner.
        
        Args:
            functions_dir: Optional directory containing function scripts to run
        """
        self.functions_dir = functions_dir
        self.processes: Dict[str, subprocess.Popen] = {}
        self.output_threads: Dict[str, List[threading.Thread]] = {}
        self.logger = logging.getLogger(__name__)
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def start_function(self, script_path: str) -> None:
        """
        Start a single function script.
        
        Args:
            script_path: Path to the Python script to run
        """
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Function script not found: {script_path}")
            
        try:
            # Set up environment
            env = os.environ.copy()
            
            # Start the process
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1
            )
            
            self.processes[script_path] = process
            
            # Start output monitoring threads
            self._start_output_threads(script_path, process)
            
            self.logger.info(f"Started function: {script_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to start function {script_path}: {str(e)}")
            raise

    def start_functions_in_directory(self) -> None:
        """
        Start all Python function scripts in the specified directory.
        """
        if not self.functions_dir:
            raise ValueError("No functions directory specified")
            
        dir_path = Path(self.functions_dir)
        if not dir_path.exists():
            raise FileNotFoundError(f"Functions directory not found: {self.functions_dir}")
            
        for script_path in dir_path.glob("*.py"):
            if script_path.name.startswith("__"):
                continue
            self.start_function(str(script_path))

    def _start_output_threads(self, script_path: str, process: subprocess.Popen) -> None:
        """
        Create threads to read and log output from the function process.
        """
        def log_output(pipe, is_error: bool):
            for line in pipe:
                line = line.strip()
                if is_error:
                    self.logger.error(f"{script_path}: {line}")
                else:
                    self.logger.info(f"{script_path}: {line}")
                    
        stdout_thread = threading.Thread(
            target=log_output,
            args=(process.stdout, False),
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=log_output,
            args=(process.stderr, True),
            daemon=True
        )
        
        self.output_threads[script_path] = [stdout_thread, stderr_thread]
        stdout_thread.start()
        stderr_thread.start()

    def _handle_shutdown(self, signum, frame) -> None:
        """
        Handle shutdown signals by stopping all functions.
        """
        self.logger.info("Received shutdown signal, stopping all functions...")
        self.stop_functions()

    def stop_functions(self) -> None:
        """
        Stop all running function processes.
        """
        for script_path, process in self.processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)  # Give process time to terminate gracefully
            except subprocess.TimeoutExpired:
                process.kill()  # Force kill if it doesn't terminate
            except Exception as e:
                self.logger.error(f"Error stopping function {script_path}: {str(e)}")
                
        self.processes.clear()
        self.output_threads.clear() 