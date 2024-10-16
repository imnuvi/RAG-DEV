"""
Module responsible for integrating python scripts execution into the BRAD system.

This module provides functions to execute python scripts based on user prompts and configuration settings. It selects the appropriate function based on user input using a large language model (LLM) and executes the selected MATLAB code.

**PYTHON Documentation Requirements**

    1. they must have full docstrings at the top of the file

    2. they must have a one line description at the top of the docstring used for selecting which code to run
"""

from langchain import PromptTemplate, LLMChain
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain
import difflib
# import matlab.engine
import os
import glob
import re
import sys
import subprocess

from BRAD.promptTemplates import pythonPromptTemplate, getPythonEditingTemplate
from BRAD import log

def callPython(chatstatus):
    """
    Executes a Python script based on the user's prompt and chat status configuration.

    This function performs the following steps:
    1. Identifies available python scripts in the specified directory.
    2. Uses an llm to select the python function that best matches the user's prompt and format code to execute the script based upon the users input.
    3. Executes the selected python function and updates the chat status.

    Parameters
    ----------
    chatstatus : dict
        A dictionary containing the chat status, including user prompt, language model (llm),
        memory, and configuration settings.

    Returns
    -------
    dict
        Updated chat status after executing the selected Python script.

    Notes
    -----
    - This function is typically called from `brad.chat()` when the `Python` module is selected by the router.
    - The Python code execution can also be initiated from `coder.codeCaller()`, which handles both Python and MATLAB scripts.
    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: June 22, 2024
    
    # Dev. Comments:
    # -------------------
    # This function is responsible for selecting a matlab function to call and
    # furmulating the function call.
    #
    # History:
    #
    # Issues:
    # - This function doesn't use the llm to select the appropriate python script.
    #   Currently, a word similarity score between the prompt and matlab codes
    #   is performed and used to select the prompts, but we could follow an approach
    #   similar to the coder.codeCaller() method that uses an llm to read the docstrings
    #   and identify the best file. Note - the same approach is used by matlabCaller
    
    log.debugLog("Python Caller Start", chatstatus=chatstatus) 
    prompt = chatstatus['prompt']                                        # Get the user prompt
    llm = chatstatus['llm']                                              # Get the llm
    memory = chatstatus['memory']
    chatstatus['process'] = {}                                           # Begin saving plotting arguments
    chatstatus['process']['name'] = 'Python'

    # Add matlab files to the path
    if chatstatus['config']['py-path'] == 'py-tutorial/': # Admittedly, I'm not sure what's going on here - JP
        pyPath = chatstatus['config']['py-path']
    else:
        base_dir = os.path.expanduser('~')
        pyPath = os.path.join(base_dir, chatstatus['config']['py-path'])
    log.debugLog('Python scripts added to PATH', chatstatus=chatstatus) 

    # Identify python scripts files we are adding to the path of BRAD
    pyScripts = find_py_files(pyPath)
    log.debugLog(pyScripts, chatstatus=chatstatus) 
    # Identify which file we should use
    pyScript = find_closest_function(prompt, pyScripts)
    log.debugLog(pyScript, chatstatus=chatstatus) 
    # Identify pyton script arguments
    pyScriptPath = os.path.join(pyPath, pyScript + '.py')
    log.debugLog(pyScriptPath, chatstatus=chatstatus) 
    # Get matlab docstrings
    pyScriptDocStrings = read_python_docstrings(pyScriptPath)
    log.debugLog(pyScriptDocStrings, chatstatus=chatstatus) 
    template = pythonPromptTemplate()
    log.debugLog(template, chatstatus=chatstatus) 
    # matlabDocStrings = callMatlab(chatstatus)
    filled_template = template.format(scriptName=pyScriptPath, scriptDocumentation=pyScriptDocStrings)
    chatstatus = log.userOutput(filled_template, chatstatus=chatstatus)
    PROMPT = PromptTemplate(input_variables=["history", "input"], template=filled_template)
    log.debugLog(PROMPT, chatstatus=chatstatus) 
    conversation = ConversationChain(prompt  = PROMPT,
                                     llm     = llm,
                                     verbose = chatstatus['config']['debug'],
                                     memory  = memory,
                                    )
    response = conversation.predict(input=chatstatus['prompt'] )
    log.debugLog('START RESPONSE', chatstatus=chatstatus) 
    log.debugLog(response, chatstatus=chatstatus) 
    log.debugLog("END RESPONSE", chatstatus=chatstatus) 
    pythonCode = extract_python_code(response, chatstatus['config']['py-path'], chatstatus)
    log.debugLog(matlabCode, chatstatus=chatstatus)
    chatstatus['process']['steps'].append(log.llmCallLog(llm             = llm,
                                                         prompt          = PROMPT,
                                                         input           = chatstatus['prompt'],
                                                         output          = response,
                                                         parsedOutput    = {
                                                             'pythonCode': pythonCode,
                                                         },
                                                         purpose         = 'formulate python function call'
                                                        )
                                         )
    execute_python_code(pythonCode, chatstatus)
    return chatstatus

def execute_python_code(python_code, chatstatus):
    """
    Executes the provided Python code and handles debug printing based on the chat status configuration.

    This function performs the following steps:
    1. Checks if `chatstatus['output-directory']` is referenced in the provided Python code; if not, replaces a specific
       part of the code with `chatstatus['output-directory']`.
    2. Attempts to evaluate the Python code using `eval()`.

    Parameters
    ----------
    python_code : str
        The Python code to be executed.

    chatstatus : dict
        A dictionary containing the chat status, including configuration settings and possibly `chatstatus['output-directory']`.

    Notes
    -----
    - This function is typically called after extracting Python code from a response in a conversational context but it can be called from the `coder.codeCaller()` as well.
    - It assumes the presence of `eval()`-compatible Python code and handles basic error handling.
    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: June 22, 2024
    log.debugLog('EVAL', chatstatus=chatstatus) 
    log.debugLog(python_code, chatstatus=chatstatus) 
    log.debugLog('END EVAL CHECK', chatstatus=chatstatus) 

    # Ensure that chatstatus['output-directory'] is passed as an argument to the code:
    if "chatstatus['output-directory']" not in python_code:
        log.debugLog('PYTHON CODE OUTPUT DIRECTORY CHANGED', chatstatus=chatstatus) 
        python_code = python_code.replace(get_arguments_from_code(python_code)[2].strip(), "chatstatus['output-directory']")
        log.debugLog(python_code, chatstatus=chatstatus) 

    # Ensure that we get the output from the script
    response = None
    python_code = "response = " + python_code
    
    try:
        # Attempt to evaluate the MATLAB code
        log.debugLog("Finalized PYTHON Call:", chatstatus=chatstatus)
        log.debugLog("   ", chatstatus=chatstatus)
        log.debugLog(python_code, chatstatus=chatstatus)
        log.debugLog("   ", chatstatus=chatstatus)

        # execute the code and get the response variable
        local_scope = {'chatstatus': chatstatus, 'sys': sys, 'subprocess': subprocess}
        exec(python_code, globals(), local_scope)
        log.debugLog("Debug: PYTHON code executed successfully.", chatstatus=chatstatus)
        response = local_scope.get('response', None)
        log.debugLog("Code Execution Output:", chatstatus=chatstatus)
        log.debugLog(response, chatstatus=chatstatus)
        chatstatus['process']['steps'].append(
            {
                'func'   : 'pythonCaller.execute_python_code',
                'code'   : python_code,
                'purpose': 'execute python code',
            }
        )
        chatstatus['output'] = response.stdout.strip()
        log.debugLog("Debug: PYTHON code output saved to output.", chatstatus=chatstatus)

        # TODO: If the response contains a stderr then we should allow it the system to
        # debug and reexecute the code
    
    except SyntaxError as se:
        log.debugLog(f"Debug: Syntax error in the PYTHON code: {se}", chatstatus=chatstatus)
    except NameError as ne:
        log.debugLog(f"Debug: Name error, possibly undefined function or variable: {ne}", chatstatus=chatstatus)
    except Exception as e:
        log.debugLog(f"Debug: An error occurred during PYTHON code execution: {e}", chatstatus=chatstatus)


# Extract the arguments from the string
def get_arguments_from_code(code):
    """
    Extracts and returns arguments from a given Python code string separated by commas.

    This function splits the input `code` string by commas to extract individual arguments
    that are typically passed to a Python script. It assumes the arguments are directly
    embedded in the provided string and separated by commas.

    Parameters
    ----------
    code : str
        The Python code or function call string containing comma-separated arguments.

    Returns
    -------
    list of str
        A list containing individual arguments extracted from the `code` string.

    Notes
    -----
    - The function does not perform validation or parsing beyond simple comma splitting.
    - It assumes the input `code` string represents valid Python syntax.

    Example
    -------
    >>> code_string = "function_name(arg1, arg2, arg3)"
    >>> arguments = get_arguments_from_code(code_string)
    >>> print(arguments)
    ['function_name(arg1', ' arg2', ' arg3)']
    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: June 22, 2024
    args_string = code.strip()
    args = args_string.split(',')
    return args

def find_py_files(path):
    """
    Recursively finds all Python (.py) files in the specified directory path.

    This function searches for all Python files (.py) in the given directory and its subdirectories,
    returning a list of the file names without their extensions.

    Parameters
    ----------
    path : str
        The directory path where the search for Python files should begin.

    Returns
    -------
    list of str
        A list of Python file names (without the .py extension) found in the specified directory.

    Notes
    -----
    - The function constructs a search pattern for .py files using `os.path.join` and `glob.glob`.
    - It searches recursively (`recursive=True`) to find all matching .py files in subdirectories.
    - The file names are extracted from the full paths and the .py extension is removed.

    Example
    -------
    >>> path = '/path/to/python/scripts'
    >>> python_files = find_py_files(path)
    >>> print(python_files)
    ['script1', 'script2', 'subdir/script3']
    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: June 22, 2024

    # Dev. Comments:
    # -------------------
    # This function executes a single user prompt with BRAD
    #
    # History:
    # - 2024-06-22: initial draft
    # - 2024-07-22: this function is modified to not use recursive search so as
    #               to allow a path list, as opposed to a single matlab path, to
    #               be used to point to where BRAD should find code

    # Construct the search pattern for .m files
    search_pattern = os.path.join(path, '*.py')
    
    # Find all .m files recursively
    py_files = glob.glob(search_pattern, recursive=False)

    # Extract only the file names from the full paths
    file_names = [os.path.basename(file)[:-3] for file in py_files]
    
    return file_names

def find_closest_function(query, functions):
    """
    Finds the closest matching function name to the query from a list of functions.

    This function uses the `difflib.get_close_matches` method to find the closest match
    to the provided query within the list of function names. It returns the best match
    if any matches are found, otherwise it returns None.

    Parameters
    ----------
    query : str
        The query string to match against the list of functions.
    functions : list of str
        The list of function names to search within.

    Returns
    -------
    str or None
        The closest matching function name if a match is found; otherwise, None.

    Notes
    -----
    - The function uses `difflib.get_close_matches` with `n=1` to find the single closest match
      and `cutoff=0.0` to include all possible matches regardless of similarity.

    Example
    -------
    >>> functions = ['analyzeData', 'processImage', 'generateReport']
    >>> query = 'analyze'
    >>> closest_function = find_closest_function(query, functions)
    >>> print(closest_function)
    'analyzeData'
    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: June 22, 2024

    # Find the closest matches to the query in the list of functions
    closest_matches = difflib.get_close_matches(query, functions, n=1, cutoff=0.0)
    
    if closest_matches:
        return closest_matches[0]
    else:
        return None

def read_python_docstrings(file_path):
    """
    Reads the docstrings from a Python file located at the given file path.

    This function extracts lines that are inside triple-quoted strings at the beginning of the file. It stops reading further lines once it encounters a line that does not belong to the docstring anymore.

    Parameters
    ----------
    file_path : str
        The path to the Python file from which to read the docstrings.

    Returns
    -------
    str
        A string containing the extracted docstrings, with each line separated by a newline character.

    Notes
    -----
    - The function assumes that the docstrings are located at the beginning of the Python file.
    - It stops reading further lines once a line that does not start with triple or double quotes
      is encountered, assuming that the docstrings are defined as per Python conventions.
    - The function preserves leading and trailing spaces in the docstring lines.

    Example
    -------
    Given a Python file '/path/to/module.py' with the following content:

    ```
    '''
    This is a sample module.

    It demonstrates how to read docstrings from a Python file.
    '''
    def my_function():
        pass
    ```

    Calling `read_python_docstrings('/path/to/module.py')` would return:
    ```
    '''
    This is a sample module.

    It demonstrates how to read docstrings from a Python file.
    '''
    ```

    If the Python file does not start with a docstring, an empty string ('') is returned.

    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: June 22, 2024

    docstring_lines = []
    inside_docstring = False
    
    with open(file_path, 'r') as file:
        for line in file:
            stripped_line = line.strip()
            if stripped_line.startswith('"""') or stripped_line.startswith("'''"):
                if inside_docstring:
                    # This ends the docstring
                    docstring_lines.append(stripped_line)
                    break
                else:
                    # This starts the docstring
                    docstring_lines.append(stripped_line)
                    inside_docstring = True
            elif inside_docstring:
                # Collect lines inside the docstring
                docstring_lines.append(line.rstrip())
            elif not stripped_line:
                # Skip any leading empty lines
                continue
            else:
                # Stop if we encounter a non-docstring line and are not inside a docstring
                break
    
    return "\n".join(docstring_lines)

def get_py_description(file_path):
    """
    Extracts a brief description from the docstrings of a Python (.py) file.

    This function reads the docstrings from the specified Python file and returns
    a one-liner description extracted typically from the second line of the docstrings.

    Parameters
    ----------
    file_path : str
        The path to the Python file from which to extract the description.

    Returns
    -------
    str
        A one-liner description extracted from the second line of the docstrings.

    Notes
    -----
    - The function assumes that the second line of the docstrings contains a brief description 
      of the Python script.
    - It uses the `read_python_docstrings` function to read the docstrings from the file.

    Example
    -------
    >>> description = get_py_description('/path/to/python/script.py')
    >>> print(description)
    ' This script demonstrates how to read docstrings from a Python file.'
    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: June 22, 2024
    docstrings = read_python_docstrings(file_path)
    oneliner = docstrings.split('\n')[1]
    return oneliner

def extract_python_code(llm_output, scriptPath, chatstatus, memory=None):
    """
    Parses the LLM output and extracts the Python code to execute.

    This function processes the output generated by an LLM (Language Model) or similar tool,
    typically extracting the final line of generated code intended for execution. It handles
    special cases where the generated code might need modification or formatting.

    Parameters:
    llm_output (str): The complete output string from the LLM tool, which includes generated Python code.

    Returns:
    str: The Python code to be executed.

    Notes:
    - The function assumes that the LLM output contains the generated Python code as the final line.
    - It may modify the format of the code for compatibility or execution purposes.
    - If the LLM output does not conform to expectations, this function may need adjustment.

    Example:
    If llm_output is:
    ```
    Some generated code...
    Execute: subprocess.call([sys.executable, 'script.py'])
    ```
    Calling `extract_python_code(llm_output, chatstatus)` would return:
    ```
    subprocess.run([sys.executable, 'script.py'])
    ```

    If the LLM output does not include a valid Python execution command, the function might modify
    or construct one based on expected patterns.
    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: June 22, 2024

    # Dev. Comments:
    # -------------------
    # This function should take llm output and extract python code
    #
    # History:
    # - 2024-06-22: initiall attempt to extract python from llms
    # - 2024-07-08: (1) strip('\'"`') is added to remove trailing quotations
    #               (2) <path/to/script> is set as a keyword to be replaced by
    #                   python paths
    #               (3) added a subsequent python call to edit the command when
    #                   compile() fails
    #
    # Issues:
    # - This is very sensitive to the particular model, prompt, and patterns in
    #   the llm response.
    
    log.debugLog("LLM OUTPUT PARSER", chatstatus=chatstatus) 
    log.debugLog(llm_output, chatstatus=chatstatus) 

    funcCall = llm_output.split('Execute:')
    log.debugLog(funcCall, chatstatus=chatstatus)
    funcCall = funcCall[len(funcCall)-1].strip()
    if funcCall.startswith('```python'):
        funcCall = funcCall.split('\n')[1]
    funcCall = funcCall.strip('\'"`') # remove specific characters (single quotes', double quotes ", and backticks `` ``) 
    
    # Ensure placeholder path is replaced
    funcCall = funcCall.replace('<path/to/script>/', scriptPath)
    funcCall = funcCall.replace('<path/to/script>',  scriptPath)
    
    log.debugLog('Stripped funciton call', chatstatus=chatstatus)
    log.debugLog(funcCall, chatstatus=chatstatus)
    
    if not funcCall.startswith('subprocess.run([sys.executable,'):
        funcCall = 'subprocess.run([sys.executable' + funcCall[funcCall.find(','):]

    log.debugLog('Cleaned up function call:\n', chatstatus=chatstatus)
    log.debugLog(funcCall, chatstatus=chatstatus)
    log.debugLog('\n', chatstatus=chatstatus)
    try:
        compile(funcCall, '<string>', 'exec')
    except Exception as e:
        return editPythonCode(funcCall, str(e), memory, chatstatus)
    
    return funcCall

def editPythonCode(funcCall, errorMessage, memory, chatstatus):
    """
    Edit the Python code based on the error message and chat status, with recursion depth limit.

    Parameters:
    funcCall (str): The Python code to be edited.
    errorMessage (str): The error message related to the code.
    chatstatus (dict): Dictionary containing chat status and configuration.

    Returns:
    str: The edited Python code ready for execution, or an error message if recursion limit is reached.
    """

    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: July 8, 2024

    # Bound the recursion depth of this function
    if chatstatus['recursion_depth'] > 5:
        log.errorLog('Recursion depth limit reached. Please check the code and error message', chatstatus=chatstatus)
        return "Recursion depth limit reached. Please check the code and error message."
    chatstatus['recursion_depth'] += 1

    # Extract the llm
    llm = chatstatus['llm']

    # Fill in the python editting template
    template = getPythonEditingTemplate()
    filled_template = template.format(
        code1 = funcCall,
        code2 = funcCall,
        error = errorMessage
    )
    log.debugLog("Memory", chatstatus=chatstatus)
    log.debugLog(memory,   chatstatus=chatstatus)
    # Build the langchain
    PROMPT          = PromptTemplate(input_variables=["history", "input"], template=filled_template)
    log.debugLog(PROMPT, chatstatus=chatstatus)
    conversation    = ConversationChain(prompt  = PROMPT,
                                        llm     =    llm,
                                        verbose = chatstatus['config']['debug'],
                                        memory  = memory,
                                       )

    # Call the llm/langchain
    response = conversation.predict(input=chatstatus['prompt'])

    # Parse the code (recursion begins here)
    code2execute = extract_python_code(response, chatstatus['config']['CODE']['path'][0], chatstatus, memory=memory)

    # log the llm output
    chatstatus['process']['steps'].append(log.llmCallLog(llm             = llm,
                                                         prompt          = PROMPT,
                                                         input           = chatstatus['prompt'],
                                                         output          = response,
                                                         parsedOutput    = {
                                                             'code': code2execute
                                                         },
                                                         purpose         = 'Edit function call'
                                                        )
                                         )
    # Decrement recursion depth after use
    chatstatus['recursion_depth'] -= 1
    return code2execute

def has_unclosed_symbols(s):
    """
    Check for unclosed symbols in a string.

    This function checks if a string has unclosed symbols such as quotes,
    parentheses, brackets, or braces. It returns True if there are unclosed
    symbols, and False otherwise.

    Parameters:
    s (str): The string to check for unclosed symbols.

    Returns:
    bool: True if there are unclosed symbols, False otherwise.
    """
    # Auth: Joshua Pickard
    #       jpic@umich.edu
    # Date: July 8, 2024
    
    stack = []
    pairs = {'(': ')', '[': ']', '{': '}'}
    opening = pairs.keys()
    closing = pairs.values()
    
    i = 0
    while i < len(s):
        char = s[i]
        if char in pairs:
            stack.append(pairs[char])
        elif char in closing:
            if not stack or char != stack.pop():
                return True
        elif char in ['"', "'"]:
            # Check if this is an escaped quote
            if i > 0 and s[i - 1] == '\\':
                i += 1
                continue
            # Toggle the quote in the stack
            if stack and stack[-1] == char:
                stack.pop()
            else:
                stack.append(char)
        i += 1
    
    return bool(stack)