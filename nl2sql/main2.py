import pandas as pd
import sqlite3
from typing import Dict
import sqlvalidator
import re
import requests

def run_query(query: str):
    """
    Executes the SQL query
    query: str = a valid SQL query
    """
    con = sqlite3.connect("Car_Database.db")
    cur = con.cursor()
    try:
        res = cur.execute(query)
        res_data = res.fetchall()
        return True, pd.DataFrame(res_data)
    except Exception as error:
        return False, error

def extract_sql_query(text: str):
    """
    Extracts SQL query from LLM output using regex. The LLM doesnt strictly output SQL code 
    The logic is to find SELECT and semi-colon (;). The LLM is prompted to always end query with semi-colon (;).
    text: str = Output from LLM
    """

    # Regex pattern to match a basic SQL query that starts with SELECT and ends with a semicolon
    pattern = r'(SELECT.*?;)' 
    # Using re.DOTALL to make the dot (.) match newlines as well
    match = re.search(pattern, text, re.DOTALL) 
    
    if match:
        return match.group(1) # Return the matched SQL query
    else:
        return None
    
def generate_sql_query(input_data: Dict, schema_info: str, with_compiler_feedback: bool):
    """
    Generates a SQL query by prompting a LLM.
    input_data: Dict = Could contain the following keys
        question: str = The natural language query
        compiler_feedback (optional): str = The error message from sqlite
    schema_info: str = The schema information of the car company database
    with_compiler_feedback: bool = If True, we change the instruction give feedback to LLM
    """


    if with_compiler_feedback:
        instruction = f"""
        For the given question {input_data['question']} you generated the following query {input_data['question']}. I got the following error upon execution {input_data['compiler_feedback']}
        With this feedback can you correct the query and generate new query.  The SQL query must end with a ;. \n Output SQL Query:
        """
    else:
        instruction = f"""
        The queries you generate should be able to understand and respond to questions phrased in natural language. The SQL query must end with a ;. Given Question: {input_data['question']} \n Output SQL Query:
        """

    input_prompt = f"""<s>[INST] In a SQLite database, there are ten distinct tables, each with its own set of columns. The tables and their respective schema are as follows: {schema_info} 
    You are tasked with generating SQL queries using these tables and their respective columns.
    {instruction} [/INST]"""
    
    from openai import OpenAI
    
    client = OpenAI(
            base_url = "https://integrate.api.nvidia.com/v1",
            api_key = "YOOUR API KEY"
            )
            
    completion = client.chat.completions.create(
            model="ibm/granite-34b-code-instruct",
            messages=[{"role":"user","content": input_prompt }],
            temperature=0.5,
            top_p=1,
            max_tokens=1024,
            stream=True
            )
    response_text = ""
    for chunk in completion:
        if chunk.choices[0].delta.content is not None:
            response_text = response_text + chunk.choices[0].delta.content


    print(response_text)
    return {
        'text': response_text,
        'success': True,
        'log': None
    }


if __name__ == "__main__":

    url = 'http://localhost:7000/v2/models/ensemble/generate'

    while 1:
        # EASY
        # question = "What are the full names and contact details of all customers?"
        # question = "What are the names of the brands that have models priced above $30,000?"

        question = input("Enter the query: \n")
        # question = "what are the customers names and pruchase price who have purchase price above $20,000?"

        # MEDIUM
        # question = "List all models along with their brands and the average purchase price."

        with open('schema.txt', 'r') as f:
            schema_info = f.read()


        # print("The query is: ",question)

        input_data = {
            'question': question,
        }

        num_attempts = 3
        for attempt_idx in range(num_attempts):

            llm_output = generate_sql_query(input_data, schema_info, with_compiler_feedback='compiler_feedback' in input_data)
            
            if llm_output['success'] is False:
                print("[INFO] SQL generation failed")
                print(f"[INFO] Got following error {llm_output['log']}")
                break

            sql_query = extract_sql_query(llm_output['text'])

            # This is also a potential feedback to LLM
            if sql_query is None:
                print("[INFO] No SQL query found")
                break

            # This could also be a potential feedback to LLM that synax is incorrect
            validator_query = sqlvalidator.parse(sql_query)
            if not validator_query.is_valid():
                print("[INFO] SQL query could not be validated")
                print(f"[INFO] SQL query: {sql_query}")
                print(f"[INFO] got the following errors {validator_query.errors}")
                break
            
        
            # print(f"[INFO] Executing the following query {sql_query}")
            print("\n \n")

            exec_success, output = run_query(sql_query)

            if exec_success:
                print("[INFO] Executed succesfully \n")
                print("Answer: \n")

                print(output)
                break
            else:
                print("[INFO] Execution failed, reattempting ..")
                print(f"[INFO] Got the following error {output}")
                input_data['compiler_feedback'] = output
