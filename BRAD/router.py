"""
Module for managing routes using the semantic_router library. This module includes functions
for reading and writing prompts, configuring routes, and building router layers with predefined routes.
"""
import os
import json
from semantic_router import Route
from semantic_router.layer import RouteLayer
from semantic_router.encoders import HuggingFaceEncoder

from langchain.prompts import PromptTemplate
from langchain_core.prompts.prompt import PromptTemplate

from BRAD.promptTemplates import rerouteTemplate
from BRAD import log
from BRAD import utils

def reroute(chatstatus):
    """
    Reroutes the conversation flow based on the current queue pointer and the user prompt. 
    It retrieves historical chat logs, incorporates them into the conversation, and determines 
    the next step in the pipeline using a language model.

    Args:
        chatstatus (dict): A dictionary containing the language model, user prompt, queue of processes, 
                           and other relevant information for rerouting the conversation.

    Returns:
        dict: The updated chatstatus containing the modified queue pointer and any logs or updates made 
              during the rerouting process.

    Example
    -------
    >>> chatstatus = {
    ...     'llm': llm_instance,
    ...     'prompt': "Reroute conversation",
    ...     'queue': [{'order': 1, 'module': 'RAG', 'prompt': '/force RAG Retrieve documents', 'description': '...'}],
    ...     'output-directory': '/path/to/output',
    ...     'process': {'steps': []}
    ... }
    >>> updated_chatstatus = reroute(chatstatus)
    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: June 24, 2024
    log.debugLog('Call to REROUTER', chatstatus=chatstatus)
    llm = chatstatus['llm']
    prompt = chatstatus['prompt']
    queue  = chatstatus['queue']

    # Build chat history
    chatlog = json.load(open(os.path.join(chatstatus['output-directory'], 'log.json')))
    history = ""
    for i in chatlog.keys():
        history += "========================================"
        history += '\n'
        history += "Input: "  + chatlog[i]['prompt']  + r'\n\n'
        history += "Output: " + chatlog[i]['output'] + r'\n\n'
    log.debugLog(history, chatstatus=chatstatus)
    
    # Put history into the conversation
    template = rerouteTemplate()
    template = template.format(chathistory=history,
                               step_number=chatstatus['queue pointer'])
    PROMPT = PromptTemplate(input_variables=["user_query"], template=template)
    chain = PROMPT | chatstatus['llm']
    res = chain.invoke(prompt)
    
    # Extract output
    log.debugLog(res, chatstatus=chatstatus)
    log.debugLog(res.content, chatstatus=chatstatus)
    # nextStep = int(res.content.split('=')[1].split('\n')[0].strip())
    nextStep = utils.find_integer_in_string(res.content.split('\n')[0])
    log.debugLog('EXTRACTED NEXT STEP', chatstatus=chatstatus)
    log.debugLog('Next Step=' + str(nextStep), chatstatus=chatstatus)
    log.debugLog(f'(nextStep is None)={(nextStep is None)}', chatstatus=chatstatus)
    if nextStep is None:
        nextStep = chatstatus['queue pointer'] + 1
    if str(nextStep) not in prompt:
        log.debugLog(f'the next step identified was not valid according to the rerouting instructions. As a result, chatstatus["queue pointer"]={chatstatus["queue pointer"]+1}', chatstatus=chatstatus)
        nextStep = chatstatus['queue pointer'] + 1
    chatstatus['process']['steps'].append(log.llmCallLog(
        llm     = llm,
        prompt  = template,
        input   = prompt,
        output  = res.content,
        parsedOutput = {'next step': nextStep},
        purpose = "Route to next step in pipeline"
    ))
    
    # Modify the queued prompts
    chatstatus['queue pointer'] = nextStep
    return chatstatus

def read_prompts(file_path):
    """
    Reads a text file where each line represents a sentence and returns a list of sentences.

    :param file_path: The path to the text file to be read.
    :type file_path: str

    :raises FileNotFoundError: If the specified file does not exist.

    :return: A list of sentences read from the text file.
    :rtype: list

    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: May 19, 2024
    sentences = []
    with open(file_path, 'r') as file:
        for line in file:
            # Strip any leading/trailing whitespace characters (including newline)
            sentence = line.strip()
            if sentence:  # Avoid adding empty lines
                sentences.append(sentence)
    return sentences

def add_sentence(file_path, sentence):
    """
    Adds a new sentence to the specified text file.

    :param file_path: The path to the text file where the sentence is to be added.
    :type file_path: str
    :param sentence: The sentence to be added to the text file.
    :type sentence: str

    :raises FileNotFoundError: If the specified file does not exist or cannot be created.

    :return: None
    :rtype: None

    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: May 19, 2024
    with open(file_path, 'a') as file:
        file.write(sentence.strip() + '\n')

def getRouterPath(file):
    """
    Constructs and returns the absolute path to a file located in the 'routers' directory.

    This function determines the current script's directory and constructs the absolute path 
    to a specified file within the 'routers' subdirectory.

    :param file: The name of the file whose path is to be constructed.
    :type file: str

    :return: The absolute path to the specified file in the 'routers' directory.
    :rtype: str
    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: June 7, 2024
    current_script_path = os.path.abspath(__file__)
    current_script_dir = os.path.dirname(current_script_path)
    file_path = os.path.join(current_script_dir, 'routers', file) #'enrichr.txt')
    return file_path
    
def getRouter():
    """
    Returns a router layer configured with predefined routes for various tasks.

    :param None: This function does not take any parameters.

    :raises None: This function does not raise any specific errors.

    :return: A router layer configured with predefined routes for tasks such as querying Enrichr, web scraping, and generating tables.
    :rtype: RouteLayer

    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: May 16, 2024
    routeGget = Route(
        name = 'GGET',
        utterances = read_prompts(getRouterPath('enrichr.txt'))
    )
    routeScrape = Route(
        name = 'SCRAPE',
        utterances = read_prompts(getRouterPath('scrape.txt'))
    )
    routeRAG = Route(
        name = 'RAG',
        utterances = read_prompts(getRouterPath('rag.txt'))
    )
    routeTable = Route(
        name = 'TABLE',
        utterances = read_prompts(getRouterPath('table.txt'))
    )
    routeData = Route(
        name = 'DATA',
        utterances = read_prompts(getRouterPath('data.txt'))
    )
    routeMATLAB = Route(
        name = 'MATLAB',
        utterances = read_prompts(getRouterPath('matlab.txt'))
    )
    routePython = Route(
        name = 'PYTHON',
        utterances = read_prompts(getRouterPath('python.txt'))
    )
    routePlanner = Route(
        name = 'PLANNER',
        utterances = read_prompts(getRouterPath('planner.txt'))
    )
    routeCode = Route(
        name = 'CODE',
        utterances = read_prompts(getRouterPath('code.txt'))
    )
    routeWrite = Route(
        name = 'WRITE',
        utterances = read_prompts(getRouterPath('write.txt'))
    )
    routeRoute = Route(
        name = 'ROUTER',
        utterances = read_prompts(getRouterPath('router.txt'))
    )
    encoder = HuggingFaceEncoder(device='cpu')
    routes = [routeGget,
              routeScrape,
              routeTable,
              routeRAG,
              routeData,
              routeMATLAB,
              routePython,
              routePlanner,
              routeCode,
              routeWrite,
              routeRoute
             ]
    router = RouteLayer(encoder=encoder, routes=routes)    
    return router

def buildRoutes(prompt):
    """
    Builds routes based on the provided prompt and updates the corresponding text files with the new prompts.

    :param prompt: The prompt containing the information to be added to the router.
    :type prompt: str

    :raises KeyError: If the specified route is not found in the paths dictionary.

    :return: None
    :rtype: None

    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: May 19, 2024
    words = prompt.split(' ')
    rebuiltPrompt = ''
    i = 0
    while i < (len(words)):
        if words[i] == '/force':
            route = words[i + 1].upper()
            i += 1
        else:
            rebuiltPrompt += (' ' + words[i])
        i += 1
    paths = {
        'DATABASE': getRouterPath('enrichr.txt'),
        'SCRAPE'  : getRouterPath('scrape.txt'),
        'RAG'     : getRouterPath('rag.txt'),
        'TABLE'   : getRouterPath('table.txt'),
        'DATA'    : getRouterPath('data.txt'),
        'SNS'     : getRouterPath('sns.txt'),
        'MATLAB'  : getRouterPath('matlab.txt'),
        'PYTHON'  : getRouterPath('python.txt'),
        'PLANNER' : getRouterPath('planner.txt'),
        'CODE'    : getRouterPath('code.txt'),
        'WRITE'   : getRouterPath('write.txt'),
        'ROUTER'  : getRouterPath('router.txt')
    }
    filepath = paths[route]
    add_sentence(filepath, rebuiltPrompt)

def getTableRouter():
    """
    .. warning:: We may be removing this soon. I don't think it is used.

    Returns a router layer configured specifically for handling table-related tasks.

    :param None: This function does not take any parameters.

    :raises None: This function does not raise any specific errors.

    :return: A router layer configured with a route for handling data-related tasks.
    :rtype: RouteLayer
    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: May 18, 2024
    encoder = HuggingFaceEncoder()
    routes = [routeData]
    router = RouteLayer(encoder=encoder, routes=routes)    
    return router