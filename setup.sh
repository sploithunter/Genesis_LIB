#!/bin/bash

# Get Python version for RTI path
PYTHON_VERSION=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')

# Set up RTI Connext DDS environment
export NDDSHOME=/Applications/rti_connext_dds-7.3.0/
export PYTHONPATH=$NDDSHOME/lib/python$PYTHON_VERSION:$PYTHONPATH
export LD_LIBRARY_PATH=$NDDSHOME/lib:$LD_LIBRARY_PATH
export DYLD_LIBRARY_PATH=$NDDSHOME/lib:$DYLD_LIBRARY_PATH

# Source RTI's environment setup script
source $NDDSHOME/resource/scripts/rtisetenv_arm64Darwin20clang12.0.bash

# Check if ANTHROPIC_API_KEY is already set
if [ ! -z "$ANTHROPIC_API_KEY" ]; then
    # Strip quotes even if already set
    ANTHROPIC_API_KEY=$(echo $ANTHROPIC_API_KEY | tr -d "'" | tr -d '"')
    export ANTHROPIC_API_KEY
else
    # Try to get it from .bash_profile
    if [ -f ~/.bash_profile ]; then
        ANTHROPIC_API_KEY=$(grep -o 'ANTHROPIC_API_KEY=.*' ~/.bash_profile | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    fi
    
    # If still not set, try .env file
    if [ -z "$ANTHROPIC_API_KEY" ] && [ -f .env ]; then
        ANTHROPIC_API_KEY=$(grep -o 'ANTHROPIC_API_KEY=.*' .env | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    fi
    
    # Export if we found it
    if [ ! -z "$ANTHROPIC_API_KEY" ]; then
        # Remove any quotes from the API key before exporting
        ANTHROPIC_API_KEY=$(echo $ANTHROPIC_API_KEY | tr -d "'" | tr -d '"')
        export ANTHROPIC_API_KEY
    else
        echo "Warning: ANTHROPIC_API_KEY not found in environment, .bash_profile, or .env file"
    fi
fi

# Check if OPENAI_API_KEY is already set
if [ ! -z "$OPENAI_API_KEY" ]; then
    # Check if it's a placeholder value
    if [[ "$OPENAI_API_KEY" == *"your"*"key"* ]] || 
       [[ "$OPENAI_API_KEY" == *"api"*"key"* ]] || 
       [[ "$OPENAI_API_KEY" == *"openai"*"key"* ]] || 
       [[ "$OPENAI_API_KEY" == *"placeholder"* ]] || 
       [[ "$OPENAI_API_KEY" == *"<"*">"* ]]; then
        echo "Warning: OPENAI_API_KEY appears to be a placeholder value. Attempting to find a real key."
        unset OPENAI_API_KEY
    else
        # Strip quotes even if already set
        OPENAI_API_KEY=$(echo $OPENAI_API_KEY | tr -d "'" | tr -d '"')
        export OPENAI_API_KEY
    fi
fi

# If OPENAI_API_KEY is not set or was a placeholder, try to get it from .bash_profile
if [ -z "$OPENAI_API_KEY" ]; then
    # Try to get it from .bash_profile using a more robust approach
    if [ -f ~/.bash_profile ]; then
        # First try the exact export line
        OPENAI_API_KEY=$(grep 'export OPENAI_API_KEY=' ~/.bash_profile | sed 's/export OPENAI_API_KEY=//')
        
        # If that doesn't work, try a more general approach
        if [ -z "$OPENAI_API_KEY" ]; then
            OPENAI_API_KEY=$(grep 'OPENAI_API_KEY=' ~/.bash_profile | sed 's/.*OPENAI_API_KEY=//')
        fi
    fi
    
    # If still not set, try .env file
    if [ -z "$OPENAI_API_KEY" ] && [ -f .env ]; then
        OPENAI_API_KEY=$(grep 'OPENAI_API_KEY=' .env | sed 's/.*OPENAI_API_KEY=//')
    fi
    
    # Export if we found it
    if [ ! -z "$OPENAI_API_KEY" ]; then
        # Remove any quotes from the API key before exporting
        OPENAI_API_KEY=$(echo $OPENAI_API_KEY | tr -d "'" | tr -d '"')
        export OPENAI_API_KEY
    else
        echo "Warning: OPENAI_API_KEY not found in environment, .bash_profile, or .env file"
        # Set a placeholder value for testing purposes
        export OPENAI_API_KEY="your_openai_api_key_here"
    fi
fi

echo "Setup complete. RTI Connext DDS environment configured."
echo "Python Version: $PYTHON_VERSION"
echo "PYTHONPATH: $PYTHONPATH"
echo "LD_LIBRARY_PATH: $LD_LIBRARY_PATH"
echo "DYLD_LIBRARY_PATH: $DYLD_LIBRARY_PATH"
if [ ! -z "$ANTHROPIC_API_KEY" ]; then
    echo "ANTHROPIC_API_KEY is set"
else
    echo "ANTHROPIC_API_KEY is not set"
fi

if [ ! -z "$OPENAI_API_KEY" ]; then
    echo "OPENAI_API_KEY is set"
else
    echo "OPENAI_API_KEY is not set"
fi

