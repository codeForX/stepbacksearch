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

# prepare the api keys
COHARE_TRIAL_API_KEY = st.secrets.get("COHARE_TRIAL_API_KEY")
BRAVE_TOKEN = st.secrets.get("BRAVE_API_KEY")

co = cohere.Client(COHARE_TRIAL_API_KEY)

client = OpenAI()
    


def prepare_string(search_results: list):
    """
    prepare the string to be displayed in the chat and to be seen by the llm
    :data: list of search results 
    :return: the string to be displayed
    """
    if len(search_results) == 0:
        return 'no results found'
    url_groups = defaultdict(list)
    for result in search_results[::-1]:
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
    :query: the question
    :snippets: the snippets to be reranked
    :top_n: the number of snippets to return
    :return: the reranked snippets
    """
    return [result.document for result in co.rerank(query,documents=snippets,top_n=top_n, model='rerank-english-v2.0')]

def descriptionBad(hostname: str, description: str) -> bool:
    """
    returns wheteher the description is bad or not
    :hostname: the hostname of the url
    :description: the description to check
    """
    host = hostname.replace('www.','').lower().strip()
    length = len(description)
    return length < 200 or (host in description.lower() and length < 400) or (description.endswith('?') and length < 400)

def prepare_snippets(results: list) -> list:
    """
    prepare the snippets to be used in the reranking
    :results: the results to be prepared
    :return: the prepared snippets
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







async def asyncBraveSearch(query, prefix='', count=20) -> list:
    """
    method to search using brave search
    :query: the query to search
    :prefix: the prefix to add to the query defaults to none
    :return: the search results
    """
    url = f"https://api.search.brave.com/res/v1/web/search?q={prefix}{query}"

    payload = {
        'count': str(count),
        'text_decorations': 'false',  
        'rich': 'true',
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
            

async def search_multiple_queries(queries, prefix='', count=20) -> list:
    """
    search multiple queries using brave search at once
    :queries: the queries to search
    :prefix: the prefix to add to the query defaults to ''
    :count: the number of results to return for each query
    :return: the search results

    """
    tasks = [asyncBraveSearch(query, prefix, count) for query in queries]

    results = await asyncio.gather(*tasks)

    combined_results = []
    for result in results:
        combined_results.extend(result)

    return combined_results


async def generated_search(messages, count=20):
    """
    generate query's to search and search them
    :messages: the messages to generate the search from
    :count: the number of results to return
    :return: the search results and the search query
    """
    search_query ={}
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
        search_query = json.loads(response.choices[0].message.content.replace("'", "\""))
        arr = await search_multiple_queries(search_query['searches'])
        snippets = prepare_snippets(arr)
        if len(snippets) <= 2 or len(snippets) <= count:
            return snippets, {}
        return rerank(search_query['question'], snippets, top_n=count), search_query
    except Exception as e:
        print(e)
        return [],{}


def use_llm(messages,sources):
    """
    ask chatgpt a question given message history and sources
    :messages: the message history
    :sources: the sources to use
    :return: the response from the llm
    """
    msgs =[]
    if sources:
        msgs = copy.deepcopy(messages)
        msgs[-1]['content'] = f'SOURCES: {sources}\n\n\n\nUSER: {msgs[-1]["content"]}'
    else:
        msgs = messages
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
