import os
import json

def read_json_file(file_path: str) -> dict:
    """Reads a JSON file and returns its contents.
    
    Args:
        file_path (str): Absolute path to the JSON file.
        
    Returns:
        dict: A dictionary containing the JSON data under 'data' and a 'status' key.
    """
    try:
        if not os.path.exists(file_path):
            return {
                "status": "error",
                "message": f"File does not exist: {file_path}"
            }
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "status": "success",
            "data": data
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to read JSON file: {str(e)}"
        }

def write_json_file(file_path: str, content: str) -> dict:
    """Writes JSON content to a file. Content must be a valid JSON string.
    
    Args:
        file_path (str): Absolute path to write the JSON file.
        content (str): JSON string or serialized representation to write.
        
    Returns:
        dict: A dictionary with 'status' and 'message' indicating outcome.
    """
    try:
        # Try parsing content to ensure it is valid JSON
        if isinstance(content, str):
            data = json.loads(content)
        else:
            data = content
            
        dir_name = os.path.dirname(file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
            
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        return {
            "status": "success",
            "message": f"Successfully wrote JSON to {file_path}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to write JSON file: {str(e)}"
        }

def read_markdown_file(file_path: str) -> dict:
    """Reads a markdown file and returns its contents.
    
    Args:
        file_path (str): Absolute path to the markdown file.
        
    Returns:
        dict: A dictionary containing the markdown text under 'content' and a 'status' key.
    """
    try:
        if not os.path.exists(file_path):
            return {
                "status": "error",
                "message": f"File does not exist: {file_path}"
            }
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        return {
            "status": "success",
            "content": text
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to read markdown file: {str(e)}"
        }

def write_markdown_file(file_path: str, content: str) -> dict:
    """Writes content to a markdown file.
    
    Args:
        file_path (str): Absolute path to write the markdown file.
        content (str): Markdown content to write.
        
    Returns:
        dict: A dictionary with 'status' and 'message' indicating outcome.
    """
    try:
        dir_name = os.path.dirname(file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
            
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return {
            "status": "success",
            "message": f"Successfully wrote markdown to {file_path}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to write markdown file: {str(e)}"
        }
