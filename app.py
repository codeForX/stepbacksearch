# pylint: disable=all
import streamlit as st
from functions import generatedSearch, askBot, prepare_string
import asyncio

    


st.title("StepBack Bot")

# Initialize chat history
if "messages" not in st.session_state:
    # store initial system prompt if not already stored
    st.session_state.messages = [{'role':'system','content':'you are an AI bot named "Mr StepBack" when you answer a question you do so by going into detail on the answer and citing your sources via markdown like [title](link)'}]


if "sources" not in st.session_state:
    # set sources to empty list if not already set
    st.session_state.sources = []



for message in st.session_state.messages:
    if message['role'] == 'system':
        continue
    with st.chat_message(message["role"]):
        
        # with st.expander("See Sources"):
        #     st.markdown(prepare_string(sources))
        st.markdown(message["content"])

if prompt := st.chat_input("What do you want to know?"):
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    # Generate search query and sources returned
    sources, query = asyncio.run(generatedSearch(st.session_state.messages,count=8))

    st.session_state.sources.append(sources)

    with st.chat_message("assistant"):
        if query:
            with st.expander("See Sources"):
                query
                st.markdown(prepare_string(sources))
        message_placeholder = st.empty()
        full_response = ""

        for token in askBot(st.session_state.messages, sources):
            full_response += (token.choices[0].delta.content or "")
            message_placeholder.markdown(full_response + "▌")
        message_placeholder.markdown(full_response)

    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": full_response})

if len(st.session_state.messages) == 1:
    # show information about the project if no messages have been sent yet
    st.markdown(
"""
Inspired by [step back prompting](https://arxiv.org/abs/2310.06117)

This is a proof of concept for a system that makes multiple searches at once to quickly find an accurate answer to the question asked by the user. This consists of a finetuned language model to generate the search query's and extract the meaning of the users question or statement, as well as a standard language model to analyze sources and return an answer and a sorting layer to minimize the amount of information the model needs to see. 

Training Dataset: [sruly/StepBackSearch](https://huggingface.co/datasets/sruly/StepBackSearch) based on [OpenAssistant/oasst1](https://huggingface.co/datasets/OpenAssistant/oasst1)

""".strip())




