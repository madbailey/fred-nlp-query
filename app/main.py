import streamlit as st
from fredapi import Fred
import os
from langchain.callbacks import StreamlitCallbackHandler
from langchain.agents import create_structured_chat_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
import google.generativeai as genai
# Import cache modules
from langchain.cache import InMemoryCache
import langchain
import time
from langchain_core.runnables.config import RunnableConfig
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure langchain cache
langchain.llm_cache = InMemoryCache()

from tools import fred_tools
from composite_tools import fred_composite_tools
from enhanced_tools import enhanced_tools  # Import the enhanced tools
from prompts import SYSTEM_PROMPT  # Import the updated system prompt

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_figure" not in st.session_state:
    st.session_state.current_figure = None
if "api_call_count" not in st.session_state:
    st.session_state.api_call_count = 0
if "last_api_call_time" not in st.session_state:
    st.session_state.last_api_call_time = 0

# Rate limiting constants
MAX_CALLS_PER_MINUTE = 10
RATE_LIMIT_WINDOW = 60  # seconds

def init_llm():
    api_key = os.getenv("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=api_key,
        temperature=0.1,
        max_output_tokens=1000,  # Reduced from 2000 to conserve quota
        cache=True,
        retry_on_failure=False,  # Changed to False to better handle rate limits manually
        convert_system_message_to_human=True,
    )
    return llm

# Create agent with more constraints
def create_agent(llm):
    from langchain.agents import AgentType, initialize_agent
    
    # Combine all tools including enhanced tools
    all_tools = fred_tools + fred_composite_tools + enhanced_tools
    
    # Create the agent using the standard initialize_agent function
    agent = initialize_agent(
        tools=all_tools,
        llm=llm,
        agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=5,  # Limit maximum iterations
        early_stopping_method="generate"
    )
    
    return agent

# Rate limiting function
def check_rate_limit():
    current_time = time.time()
    time_passed = current_time - st.session_state.last_api_call_time
    
    # Reset counter if window has passed
    if time_passed > RATE_LIMIT_WINDOW:
        st.session_state.api_call_count = 0
        st.session_state.last_api_call_time = current_time
        return True
    
    # Check if we've exceeded our rate limit
    if st.session_state.api_call_count >= MAX_CALLS_PER_MINUTE:
        wait_time = RATE_LIMIT_WINDOW - time_passed
        if wait_time > 0:
            return False
        else:
            # Reset after waiting
            st.session_state.api_call_count = 0
            st.session_state.last_api_call_time = current_time
            return True
    
    # Increment counter and update time
    st.session_state.api_call_count += 1
    return True

# Streamlit UI
def load_css():
    st.markdown("""
        <style>
            .economic-card {
                padding: 20px;
                border-radius: 10px;
                background-color: #f5f5f0; /* New secondaryBackgroundColor */
                /* Consider a more subtle border or no shadow for XKCD style */
                border: 1px solid #dddddd; /* Example border */
                margin-bottom: 20px;
            }
            .chart-container {
                background-color: #f5f5f0; /* New secondaryBackgroundColor */
                padding: 15px;
                border-radius: 10px;
                /* Consider a more subtle border or no shadow */
                border: 1px solid #dddddd; /* Example border */
            }
        </style>
    """, unsafe_allow_html=True)

# Use at top of app
load_css()

# Main App UI
st.title("FRED BUDDY")
st.write("Hi, I'm FRED BUDDY! Ask me questions about economic data, and I'll help you find and visualize it.")

# Initialize LLM and agent (only once)
if "agent" not in st.session_state:
    with st.spinner("Initializing AI model..."):
        llm = init_llm()
        st.session_state.agent = create_agent(llm)

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # Display figure if this message has one and it's from the assistant
        if message["role"] == "assistant" and "figure" in message:
            st.pyplot(message["figure"])

# Chat input
if prompt := st.chat_input("What would you like to know about economic data?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
        
    # Generate and display assistant response
    with st.chat_message("assistant"):
        st_callback = StreamlitCallbackHandler(st.container())
        
        # Check rate limits
        if not check_rate_limit():
            st.warning("Rate limit exceeded. Please wait a moment before trying again.")
            st.session_state.messages.append({
                "role": "assistant", 
                "content": "I'm currently experiencing high traffic. Please try again in a minute to avoid rate limiting."
            })
        else:
            try:
                with st.spinner("Thinking..."):
                    # Configure with timeout to prevent hanging
                    config = RunnableConfig(
                        callbacks=[st_callback],
                        max_concurrency=1,
                        timeout=15  # Set timeout in seconds
                    )
                    
                    response = st.session_state.agent.invoke(
                        {"input": prompt},
                        config
                    )
                    response_text = response["output"]
                    
                    st.markdown(response_text)

                    with st.expander("View Agent's Reasoning"):
                        if "intermediate_steps" in response:
                            for step in response["intermediate_steps"]:
                                action, observation = step
                                st.write(f"**Tool used:** {action.tool}")
                                st.write(f"**Action input:** {action.tool_input}")
                                st.write(f"**Observation:** {observation}")
                                st.write("---")
                
                    # If there's a figure to display
                    if st.session_state.current_figure is not None:
                        st.pyplot(st.session_state.current_figure)
                        
                        # Add message with figure to history
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": response_text,
                            "figure": st.session_state.current_figure
                        })
                        
                        # Clear current figure
                        st.session_state.current_figure = None
                    else:
                        # Add message without figure to history
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": response_text
                        })
            except Exception as e:
                error_message = f"An error occurred: {str(e)}"
                logger.error(error_message)
                st.error(error_message)
                
                # Provide a fallback response that doesn't require API calls
                if "429" in str(e) or "Resource" in str(e):
                    fallback = "I'm experiencing API rate limits right now. Please try again in a minute."
                else:
                    fallback = "I encountered an error processing your request. Please try a simpler query or try again later."
                
                st.markdown(fallback)
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": fallback
                })