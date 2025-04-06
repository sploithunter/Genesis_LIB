#!/usr/bin/env python3
"""
Enhanced GENESIS Monitoring Application V2.6

This application monitors the enhanced monitoring topics (ComponentLifecycleEvent,
ChainEvent, and LivelinessUpdate) using the new event categorization system to provide 
a unified view of the GENESIS distributed system state.
"""

import argparse
import logging
import sys
import time
import os
import json
from datetime import datetime
import threading
import curses
from enum import Enum
import rti.connextdds as dds
import re
from genesis_lib.utils import get_datamodel_path

# Color pairs for different event types
EVENT_COLOR_PAIRS = {
    # Discovery Events
    "NODE_DISCOVERY": 1,     # White on Blue
    "EDGE_DISCOVERY": 2,     # Black on Cyan
    "STATE_CHANGE": 3,       # Black on Green
    
    # Chain Events
    "CALL_START": 4,         # White on Blue
    "CALL_COMPLETE": 5,      # Black on Green
    "CALL_ERROR": 6,         # White on Red
    "LLM_CALL_START": 7,     # White on Magenta
    "LLM_CALL_COMPLETE": 8,  # Black on Cyan
    "CLASSIFICATION_RESULT": 9, # White on Yellow
    
    # States (for STATE_CHANGE events)
    "JOINING": 10,           # White on Blue
    "DISCOVERING": 11,       # Black on Cyan
    "READY": 12,            # Black on Green
    "BUSY": 13,             # Black on Yellow
    "DEGRADED": 14,         # White on Red
    "OFFLINE": 15,          # White on default
    
    "UNKNOWN": 0            # Default color
}

class ComponentLifecycleListener(dds.DynamicData.NoOpDataReaderListener):
    """Custom listener for ComponentLifecycleEvent topic."""
    
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.logger = logging.getLogger("ComponentLifecycleListener")
        self.logger.setLevel(logging.DEBUG)
    
    def on_data_available(self, reader):
        """Handle received data."""
        try:
            samples = reader.take()
            print(f"Got {len(samples)} samples", file=sys.stderr)
            
            for data, info in samples:
                if data is None or info.state.instance_state != dds.InstanceState.ALIVE:
                    continue
                
                print(f"\nRAW DDS DATA:", file=sys.stderr)
                print(f"Capabilities: {data['capabilities']}", file=sys.stderr)
                print(f"Reason: {data['reason']}", file=sys.stderr)
                
                print(f"\nProcessing sample: {data}", file=sys.stderr)
                
                # Map component types and states
                component_types = ["INTERFACE", "PRIMARY_AGENT", "SPECIALIZED_AGENT", "FUNCTION"]
                states = ["JOINING", "DISCOVERING", "READY", "BUSY", "DEGRADED", "OFFLINE"]
                event_categories = ["NODE_DISCOVERY", "EDGE_DISCOVERY", "STATE_CHANGE", "AGENT_INIT", "AGENT_READY", "AGENT_SHUTDOWN", "DDS_ENDPOINT"]
                
                # Convert enum values to integers for indexing
                component_type_idx = int(data["component_type"])
                previous_state_idx = int(data["previous_state"])
                new_state_idx = int(data["new_state"])
                event_category_idx = int(data["event_category"])
                
                # Safely get event category
                event_category = event_categories[event_category_idx] if 0 <= event_category_idx < len(event_categories) else "UNKNOWN"
                
                # Build data dictionary with new format fields
                data_dict = {
                    "event_category": event_category,
                    "component_id": data["component_id"],
                    "component_type": component_types[component_type_idx],
                    "previous_state": states[previous_state_idx],
                    "new_state": states[new_state_idx],
                    "timestamp": data["timestamp"],
                    "source_id": str(data["source_id"]) if data["source_id"] else "",
                    "target_id": str(data["target_id"]) if data["target_id"] else "",
                    "connection_type": str(data["connection_type"]) if data["connection_type"] else "",
                    "chain_id": data["chain_id"],
                    "call_id": data["call_id"],
                    "capabilities": data["capabilities"],
                    "reason": data["reason"]
                }
                
                if self.callback:
                    self.callback(data_dict)
                    
        except Exception as e:
            print(f"Error in ComponentLifecycleListener: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

class ChainEventListener(dds.DynamicData.NoOpDataReaderListener):
    """Custom listener for ChainEvent topic."""
    
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.logger = logging.getLogger("ChainEventListener")
        self.logger.setLevel(logging.DEBUG)
    
    def on_data_available(self, reader):
        """Handle received data."""
        try:
            samples = reader.take()
            print(f"\nChainEventListener: Got {len(samples)} samples", file=sys.stderr)
            
            for data, info in samples:
                if data is None or info.state.instance_state != dds.InstanceState.ALIVE:
                    continue
                
                data_dict = {
                    "event_type": data["event_type"],
                    "chain_id": data["chain_id"],
                    "source_id": data["source_id"],
                    "target_id": data["target_id"],
                    "function_id": data["function_id"],
                    "timestamp": data["timestamp"],
                    "status": data["status"],
                    "call_id": data["call_id"]
                }
                
                if self.callback:
                    self.callback(data_dict)
                    
        except Exception as e:
            print(f"Error in ChainEventListener: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

class MonitoringAppV2_6:
    """
    Terminal-based monitoring application for GENESIS V2.6.
    Displays monitoring events using the new event categorization system.
    """
    def __init__(self, domain_id=0, max_entries=1000):
        """Initialize the monitoring application."""
        self.domain_id = domain_id
        self.max_entries = max_entries
        self.entries = []
        self.entries_lock = threading.Lock()
        
        # Display control
        self.paused = False
        self.quit_flag = False
        self.show_details = False
        self.scroll_position = 0
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            filename='genesis_monitor_v2.6.log'
        )
        self.logger = logging.getLogger("MonitoringAppV2.6")
        
        # Create DDS entities
        print(f"\nInitializing DDS on domain {domain_id}", file=sys.stderr)
        self.participant = dds.DomainParticipant(domain_id)
        self.subscriber = dds.Subscriber(self.participant)
        
        # Get type provider
        print("Loading types from datamodel.xml", file=sys.stderr)
        provider = dds.QosProvider(get_datamodel_path())
        
        # Set up ComponentLifecycleEvent subscriber
        print("Creating ComponentLifecycleEvent topic", file=sys.stderr)
        self.lifecycle_type = provider.type("genesis_lib", "ComponentLifecycleEvent")
        self.lifecycle_topic = dds.DynamicData.Topic(
            self.participant,
            "ComponentLifecycleEvent",
            self.lifecycle_type
        )
        
        # Set up ChainEvent subscriber
        print("Creating ChainEvent topic", file=sys.stderr)
        self.chain_type = provider.type("genesis_lib", "ChainEvent")
        self.chain_topic = dds.DynamicData.Topic(
            self.participant,
            "ChainEvent",
            self.chain_type
        )
        
        # Configure reader QoS
        reader_qos = dds.QosProvider.default.datareader_qos
        reader_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
        reader_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
        reader_qos.history.kind = dds.HistoryKind.KEEP_LAST
        reader_qos.history.depth = 1000
        
        # Create readers with listeners
        self.lifecycle_listener = ComponentLifecycleListener(self._lifecycle_callback)
        self.lifecycle_reader = dds.DynamicData.DataReader(
            subscriber=self.subscriber,
            topic=self.lifecycle_topic,
            qos=reader_qos,
            listener=self.lifecycle_listener,
            mask=dds.StatusMask.DATA_AVAILABLE
        )
        
        self.chain_listener = ChainEventListener(self._chain_callback)
        self.chain_reader = dds.DynamicData.DataReader(
            subscriber=self.subscriber,
            topic=self.chain_topic,
            qos=reader_qos,
            listener=self.chain_listener,
            mask=dds.StatusMask.DATA_AVAILABLE
        )
    
    def _lifecycle_callback(self, data):
        """Handle received lifecycle events."""
        with self.entries_lock:
            entry = {
                "type": "lifecycle",
                "data": data,
                "timestamp": data["timestamp"]
            }
            self._add_entry(entry)
    
    def _chain_callback(self, data):
        """Handle received chain events."""
        with self.entries_lock:
            entry = {
                "type": "chain",
                "data": data,
                "timestamp": data["timestamp"]
            }
            self._add_entry(entry)
    
    def _add_entry(self, entry):
        """Add an entry to the list and maintain max size."""
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
    
    def run_curses(self, stdscr):
        """Run the monitoring application with curses interface."""
        # Initialize curses
        curses.curs_set(0)
        curses.use_default_colors()
        stdscr.keypad(True)
        
        # Initialize color pairs
        self._init_color_pairs()
        
        # Get screen dimensions
        max_y, max_x = stdscr.getmaxyx()
        
        # Create windows
        header_win = curses.newwin(3, max_x, 0, 0)
        main_win = curses.newwin(max_y - 5, max_x, 3, 0)
        status_win = curses.newwin(2, max_x, max_y - 2, 0)
        
        # Enable scrolling in main window
        main_win.scrollok(True)
        
        # Main loop
        refresh_interval = 0.1
        last_refresh = 0
        
        while not self.quit_flag:
            current_time = time.time()
            
            if not self.paused or current_time - last_refresh >= 1.0:
                self._update_header(header_win, max_x)
                self._update_main_window(main_win, max_y, max_x)
                self._update_status(status_win, max_x)
                last_refresh = current_time
            
            key = self._handle_input(stdscr)
            if key == ord('q'):
                self.quit_flag = True
            elif key == ord('p'):
                self.paused = not self.paused
            elif key == ord('c'):
                with self.entries_lock:
                    self.entries = []
            elif key == ord('d'):
                self.show_details = not self.show_details
            
            time.sleep(refresh_interval)
    
    def _init_color_pairs(self):
        """Initialize color pairs for different event types."""
        # Discovery Events
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)    # NODE_DISCOVERY
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)    # EDGE_DISCOVERY
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_GREEN)   # STATE_CHANGE
        
        # Chain Events
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)    # CALL_START
        curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_GREEN)   # CALL_COMPLETE
        curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_RED)     # CALL_ERROR
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_MAGENTA) # LLM_CALL_START
        curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_CYAN)    # LLM_CALL_COMPLETE
        curses.init_pair(9, curses.COLOR_WHITE, curses.COLOR_YELLOW)  # CLASSIFICATION_RESULT
        
        # States
        curses.init_pair(10, curses.COLOR_WHITE, curses.COLOR_BLUE)   # JOINING
        curses.init_pair(11, curses.COLOR_BLACK, curses.COLOR_CYAN)   # DISCOVERING
        curses.init_pair(12, curses.COLOR_BLACK, curses.COLOR_GREEN)  # READY
        curses.init_pair(13, curses.COLOR_BLACK, curses.COLOR_YELLOW) # BUSY
        curses.init_pair(14, curses.COLOR_WHITE, curses.COLOR_RED)    # DEGRADED
        curses.init_pair(15, curses.COLOR_WHITE, -1)                  # OFFLINE
    
    def _format_event_line(self, data, event_type, max_x):
        """Format an event line based on its type."""
        timestamp = datetime.fromtimestamp(data["timestamp"] / 1000).strftime("%H:%M:%S.%f")[:-3]
        
        if event_type == "lifecycle":
            category = data["data"]["event_category"]
            if category == "NODE_DISCOVERY":
                # Try to extract function name from capabilities
                capabilities = {}
                try:
                    capabilities = json.loads(data['data']['capabilities'])
                except:
                    pass
                
                # Get display name from capabilities
                display_name = None
                if isinstance(capabilities, dict):
                    display_name = capabilities.get("function_name")
                
                component_info = f"{data['data']['component_id']}"
                if display_name:
                    component_info = f"{display_name} ({component_info})"
                
                event_line = f"[{timestamp}] [NODE.DISCOVERY] Component: {component_info} ({data['data']['component_type']})"
                color = EVENT_COLOR_PAIRS["NODE_DISCOVERY"]
            elif category == "EDGE_DISCOVERY":
                # Try to extract function name from capabilities for edges
                capabilities = {}
                try:
                    capabilities = json.loads(data['data']['capabilities'])
                except:
                    pass
                
                # Get function name from capabilities if available
                function_name = ""
                if isinstance(capabilities, dict):
                    function_name = capabilities.get("function_name", "")
                    if function_name:
                        function_name = f" [{function_name}]"
                
                event_line = f"[{timestamp}] [EDGE.DISCOVERY] {data['data']['connection_type']}: {data['data']['source_id']} -> {data['data']['target_id']}{function_name}"
                color = EVENT_COLOR_PAIRS["EDGE_DISCOVERY"]
            elif category == "STATE_CHANGE":
                event_line = f"[{timestamp}] [STATE.CHANGE] {data['data']['component_id']}: {data['data']['previous_state']} -> {data['data']['new_state']}"
                color = EVENT_COLOR_PAIRS[data['data']['new_state']]
            elif category == "AGENT_INIT":
                event_line = f"[{timestamp}] [AGENT.INIT] {data['data']['component_id']}: {data['data']['reason']}"
                color = EVENT_COLOR_PAIRS["JOINING"]
            elif category == "AGENT_READY":
                event_line = f"[{timestamp}] [AGENT.READY] {data['data']['component_id']}: {data['data']['reason']}"
                color = EVENT_COLOR_PAIRS["READY"]
            elif category == "AGENT_SHUTDOWN":
                event_line = f"[{timestamp}] [AGENT.SHUTDOWN] {data['data']['component_id']}: {data['data']['reason']}"
                color = EVENT_COLOR_PAIRS["OFFLINE"]
            elif category == "DDS_ENDPOINT":
                event_line = f"[{timestamp}] [DDS.ENDPOINT] {data['data']['component_id']}: {data['data']['reason']}"
                color = EVENT_COLOR_PAIRS["DISCOVERING"]
            else:
                event_line = f"[{timestamp}] [{category}] {data['data']['component_id']}: {data['data']['reason']}"
                color = EVENT_COLOR_PAIRS["UNKNOWN"]
        else:  # chain event
            event_type = data["data"]["event_type"]
            chain_id = data["data"]["chain_id"][:8]
            source = data["data"]["source_id"]
            target = data["data"]["target_id"]
            function_id = data["data"]["function_id"]
            
            if "LLM" in event_type:
                prefix = "[LLM.BASE]" if "classifier" not in function_id.lower() else "[LLM.CLASSIFIER]"
            else:
                prefix = "[CHAIN]"
            
            event_line = f"[{timestamp}] {prefix} [{event_type}] Chain {chain_id}: {source} -> {target}"
            if function_id:
                event_line += f" [{function_id}]"
            
            color = EVENT_COLOR_PAIRS.get(event_type, EVENT_COLOR_PAIRS["UNKNOWN"])
        
        if len(event_line) > max_x - 2:
            event_line = event_line[:max_x - 5] + "..."
        
        return event_line, color
    
    def _count_lines_lifecycle(self, data, show_details):
        """Count how many lines a lifecycle event will take."""
        lines = 1  # Main event line
        
        if show_details:
            # Add lines for each detail
            if data["event_category"] == "NODE_DISCOVERY":
                lines += 1  # Component Type
                try:
                    capabilities = json.loads(data['capabilities'])
                    if isinstance(capabilities, dict):
                        if "function_name" in capabilities:
                            lines += 1
                        if "description" in capabilities:
                            lines += 1
                except:
                    pass
            elif data["event_category"] == "EDGE_DISCOVERY":
                lines += 1  # Connection Type
                lines += 1  # Source
                lines += 1  # Target
                try:
                    capabilities = json.loads(data['capabilities'])
                    if isinstance(capabilities, dict) and "function_name" in capabilities:
                        lines += 1
                except:
                    pass
            elif data["event_category"] == "STATE_CHANGE":
                lines += 1  # Previous State
                lines += 1  # New State
            
            # Common details
            if data["chain_id"]:
                lines += 1
            if data["call_id"]:
                lines += 1
            if data.get("reason"):
                lines += 1
        
        return lines
    
    def _count_lines_chain(self, data, show_details):
        """Count how many lines a chain event will take."""
        lines = 1  # Main event line
        
        if show_details:
            if data.get("function_id"):
                lines += 1
            if data.get("source_id"):
                lines += 1
            if data.get("target_id"):
                lines += 1
            if data.get("status") is not None:
                lines += 1
            if data.get("chain_id"):
                lines += 1
            if data.get("call_id"):
                lines += 1
        
        return lines
    
    def _update_main_window(self, win, max_y, max_x):
        """Update the main display window."""
        win.clear()
        
        with self.entries_lock:
            # Calculate total lines needed for all entries
            total_lines = 0
            line_counts = []  # Store number of lines each entry will take
            
            # First pass - count lines
            for entry in sorted(self.entries, key=lambda x: x["timestamp"]):
                if entry["type"] == "lifecycle":
                    lines = self._count_lines_lifecycle(entry["data"], self.show_details)
                else:  # chain
                    lines = self._count_lines_chain(entry["data"], self.show_details)
                line_counts.append(lines)
                total_lines += lines
            
            # Calculate valid scroll range
            max_scroll = max(0, total_lines - (max_y - 5))
            self.scroll_position = min(max_scroll, self.scroll_position)
            self.scroll_position = max(0, self.scroll_position)
            
            # Find starting entry and offset
            current_line = 0
            start_entry = 0
            start_line_offset = 0
            
            sorted_entries = sorted(self.entries, key=lambda x: x["timestamp"])
            
            # Find which entry to start displaying from
            for i, count in enumerate(line_counts):
                if current_line + count > self.scroll_position:
                    start_entry = i
                    start_line_offset = self.scroll_position - current_line
                    break
                current_line += count
            
            # Display entries
            display_line = 0
            for i in range(start_entry, len(sorted_entries)):
                if display_line >= max_y - 5:
                    break
                
                entry = sorted_entries[i]
                event_line, color = self._format_event_line(entry, entry["type"], max_x)
                
                try:
                    # Skip lines for the first entry if there's an offset
                    if i == start_entry and start_line_offset > 0:
                        if display_line - start_line_offset >= 0:
                            win.addstr(display_line - start_line_offset, 0, event_line, curses.color_pair(color))
                    else:
                        win.addstr(display_line, 0, event_line, curses.color_pair(color))
                    display_line += 1
                    
                    if self.show_details:
                        if entry["type"] == "lifecycle":
                            details = self._get_lifecycle_details(entry["data"])
                        else:
                            details = self._get_chain_details(entry["data"])
                        
                        for detail in details:
                            if display_line >= max_y - 5:
                                break
                            if i == start_entry and start_line_offset > 0:
                                if display_line - start_line_offset >= 0:
                                    win.addstr(display_line - start_line_offset, 2, detail[:max_x-3])
                            else:
                                win.addstr(display_line, 2, detail[:max_x-3])
                            display_line += 1
                except curses.error:
                    pass
        
        win.refresh()
    
    def _get_lifecycle_details(self, data):
        """Get formatted details for a lifecycle event."""
        details = []
        
        # Add category-specific details
        if data["event_category"] == "NODE_DISCOVERY":
            details.append(f"Component Type: {data['component_type']}")
            
            # Try to extract function name from capabilities
            try:
                capabilities = json.loads(data['capabilities'])
                if isinstance(capabilities, dict) and "function_name" in capabilities:
                    details.append(f"Function Name: {capabilities['function_name']}")
                if "description" in capabilities:
                    details.append(f"Description: {capabilities['description']}")
            except:
                pass
                
        elif data["event_category"] == "EDGE_DISCOVERY":
            details.append(f"Connection Type: {data['connection_type']}")
            details.append(f"Source: {data['source_id']}")
            details.append(f"Target: {data['target_id']}")
            
            # Try to extract function name from capabilities for edges
            try:
                capabilities = json.loads(data['capabilities'])
                if isinstance(capabilities, dict) and "function_name" in capabilities:
                    details.append(f"Function: {capabilities['function_name']}")
            except:
                pass
                
        elif data["event_category"] == "STATE_CHANGE":
            details.append(f"Previous State: {data['previous_state']}")
            details.append(f"New State: {data['new_state']}")
        
        # Add common details if they exist
        if data["chain_id"]:
            details.append(f"Chain ID: {data['chain_id']}")
        if data["call_id"]:
            details.append(f"Call ID: {data['call_id']}")
        if data.get("reason"):
            details.append(f"Reason: {data['reason']}")
        
        return details
    
    def _get_chain_details(self, data):
        """Get formatted details for a chain event."""
        details = []
        
        # Add chain-specific details
        if data.get("function_id"):
            details.append(f"Function: {data['function_id']}")
        if data.get("source_id"):
            details.append(f"Source: {data['source_id']}")
        if data.get("target_id"):
            details.append(f"Target: {data['target_id']}")
        if data.get("status"):
            details.append(f"Status: {data['status']}")
        if data.get("chain_id"):
            details.append(f"Chain ID: {data['chain_id']}")
        if data.get("call_id"):
            details.append(f"Call ID: {data['call_id']}")
        
        return details
    
    def _update_header(self, win, max_x):
        """Update the header window."""
        win.clear()
        title = " GENESIS Monitor V2.6 "
        domain = f" Domain: {self.domain_id} "
        status = "PAUSED" if self.paused else "RUNNING"
        
        win.addstr(0, 0, title, curses.A_BOLD)
        win.addstr(0, max_x - len(domain), domain, curses.A_BOLD)
        win.addstr(1, 0, f" Status: {status} | Press [q]uit | [p]ause | [c]lear | [d]etails")
        win.refresh()
    
    def _update_status(self, win, max_x):
        """Update the status window."""
        win.clear()
        
        with self.entries_lock:
            total_events = len(self.entries)
            lifecycle_events = sum(1 for e in self.entries if e["type"] == "lifecycle")
            chain_events = sum(1 for e in self.entries if e["type"] == "chain")
        
        status_line = f" Events: {total_events} | Lifecycle: {lifecycle_events} | Chain: {chain_events}"
        if len(status_line) < max_x:
            status_line += " | Press 'd' to toggle details"
        
        win.addstr(0, 0, status_line)
        win.refresh()
    
    def _handle_input(self, stdscr):
        """Handle keyboard input."""
        stdscr.timeout(100)
        try:
            key = stdscr.getch()
            if key == curses.KEY_UP:
                self.scroll_position = max(0, self.scroll_position - 1)
            elif key == curses.KEY_DOWN:
                self.scroll_position += 1
            elif key == curses.KEY_PPAGE:  # Page Up
                self.scroll_position = max(0, self.scroll_position - 10)
            elif key == curses.KEY_NPAGE:  # Page Down
                self.scroll_position += 10
            return key
        except:
            return -1
    
    def run(self):
        """Run the monitoring application."""
        try:
            curses.wrapper(self.run_curses)
        except KeyboardInterrupt:
            print("\nShutting down...")
        except Exception as e:
            print(f"Exception occurred: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
        finally:
            self.logger.info("Shutting down monitoring application")
            if hasattr(self, 'lifecycle_reader'):
                self.lifecycle_reader.close()
            if hasattr(self, 'chain_reader'):
                self.chain_reader.close()
            if hasattr(self, 'participant'):
                self.participant.close()

def main():
    """Main entry point for the monitoring application."""
    parser = argparse.ArgumentParser(description="GENESIS Monitoring Application V2.6")
    parser.add_argument("--domain", type=int, default=0, help="DDS domain ID")
    parser.add_argument("--max-entries", type=int, default=1000,
                       help="Maximum number of entries to keep in memory")
    args = parser.parse_args()
    
    app = MonitoringAppV2_6(
        domain_id=args.domain,
        max_entries=args.max_entries
    )
    app.run()

if __name__ == "__main__":
    main() 