import copy
import asyncio
from collections import defaultdict
# from bs4 import BeautifulSoup
import requests
import json
import os
import cohere
import re
import aiohttp
import asyncio

from openai import OpenAI
import streamlit as st
# load_dotenv()
COHARE_TRIAL_API_KEY = st.secrets.get("COHARE_TRIAL_API_KEY")
co = cohere.Client(COHARE_TRIAL_API_KEY)
BRAVE_TOKEN = st.secrets.get("BRAVE_API_KEY")
client = OpenAI()
    


def prepare_string(data: list):
    """
    prepare the string to be displayed in the chat and to be seen by the llm
    """
    if len(data) == 0:
        return 'no results found'
    url_groups = defaultdict(list)
    for result in data[::-1]:
        url_groups[result['url']].append(result)
    output = ""
    for url, results in url_groups.items():
        output += '-' * 48 + "\n"
        output += results[0]['title'] + "\n"
        output += url + "\n"
        
        for index, result in enumerate(results):
            if index != 0:
                output += '...\n'
            output += result['text'] + "\n"
    
        if len(results) == results[0]['snippetCount']:
            output += '\n* no more info on this page available\n' 
        else:
            output += '\n* more info is availible\n'
    output += '-' * 3 + "\n"
    return output



def rerank(query,snippets, top_n=10):
    """
    method to rerank the snippets according to what is most likely to help answer the question
    """
    return [result.document for result in co.rerank(query,documents=snippets,top_n=top_n, model='rerank-english-v2.0')]

def descriptionBad(hostname: str, description: str) -> bool:
    """
    returns whetehr the description is bad or not
    """
    host = hostname.replace('www.','').lower().strip()
    length = len(description)
    return length < 200 or (host in description.lower() and length < 400) or (description.endswith('?') and length < 400)

def prepare_snippets(results: list) -> list:
    """
    prepare the snippets to be used in the reranking
    """
    snippets = []
    for result in results:
        host = result['meta_url']['hostname']
        host = host.replace('www.','').lower().strip()
        if 'extra_snippets' in result:
            if len(result['extra_snippets']) == 1 and descriptionBad(host, result['extra_snippets'][0]):
                continue
            snippetCount = len(result['extra_snippets'])
            snippets.extend({'text':snippet,'url':result['url'],'title':result['title'],'snippetCount':snippetCount} for snippet in result['extra_snippets']) 
        else:
            if descriptionBad(host, result['description']):
                continue
            snippets.append({'text':result['description'],'url':result['url'],'title':result['title'],'snippetCount':1})
    return snippets







async def asyncBraveSearch(query, prefix='', count=20):
    """
    method to search using brave search
    
    """
    url = f"https://api.search.brave.com/res/v1/web/search?q={prefix}{query}"

    payload = {
        'count': str(count),
        'text_decorations': 'false',  # Convert boolean to lowercase string
        'rich': 'true',               # Convert boolean to lowercase string
        'result_filter': 'web',
    }
    headers = {
        'X-Subscription-Token': BRAVE_TOKEN,
        'Cookie': 'search_api_csrftoken=<your-csrf-token>'
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=payload) as response:
            if response.status == 200:
                response_json = await response.json()
                return response_json.get('web', {}).get('results', [])
            else:
                return []
            

async def searchMultipleQueries(queries, prefix='', count=20):
    """
    search multiple queries using brave search at once
    """
    tasks = [asyncBraveSearch(query, prefix, count) for query in queries]

    results = await asyncio.gather(*tasks)

    combined_results = []
    for result in results:
        combined_results.extend(result)

    return combined_results


async def generatedSearch(messages, count=20):
    """
    generate querys to search and search them
    """
    searchQuery ={}
    try:
        msgs = copy.deepcopy(messages)
        msgs[-1]['content'] +='\n[SEARCH]'
        response = client.chat.completions.create(
            model="ft:gpt-3.5-turbo-1106:personal::8L1eiJr0",
            messages=msgs,
            temperature=0,
            max_tokens=512,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )
        searchQuery = json.loads(response.choices[0].message.content.replace("'", "\""))
        arr = await searchMultipleQueries(searchQuery['searches'])
        snippets = prepare_snippets(arr)
        if len(snippets) <= 2 or len(snippets) <= count:
            return snippets, {}
        return rerank(searchQuery['question'], snippets, top_n=count), searchQuery
    except Exception as e:
        print(e)
        return [],{}


def askBot(messages,sources):
    """
    ask chatgpt a question given message history and sources
    """
    msgs =[]
    if sources:
        msgs = copy.deepcopy(messages)
        msgs[-1]['content'] = f'SOURCES: {sources}\n\n\n\nUSER: {msgs[-1]["content"]}'
    else:
        msgs = messages
    print(msgs)
    return client.chat.completions.create(
    model="gpt-4-1106-preview",
    messages=msgs,
    temperature=0,
    max_tokens=1080,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0,
    stream=True,
   )