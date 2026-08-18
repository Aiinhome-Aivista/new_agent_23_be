import json
import urllib.request
import urllib.parse
import base64
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class JiraConnectionRequest(BaseModel):
    url: str
    email: str
    token: str
    jql: Optional[str] = "assignee=currentUser() AND statusCategory != Done"

@router.post("/tickets")
async def fetch_jira_tickets(payload: JiraConnectionRequest):
    try:
        base_url = payload.url.rstrip('/')
        api_url = f"{base_url}/rest/api/3/search/jql"
        
        jql_query = payload.jql if payload.jql else "assignee=currentUser()"
        params = urllib.parse.urlencode({
            "jql": jql_query,
            "maxResults": 20,
            "fields": "summary,description,issuetype,status"
        })
        
        full_url = f"{api_url}?{params}"
        
        # Prepare auth header
        auth_str = f"{payload.email}:{payload.token}"
        auth_b64 = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
        
        req = urllib.request.Request(full_url)
        req.add_header("Authorization", f"Basic {auth_b64}")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
            
        tickets = []
        for issue in data.get("issues", []):
            fields = issue.get("fields", {})
            
            # Safely get description (Jira API v3 might return Atlassian Document Format, but v2 usually returns string)
            desc = fields.get("description", "")
            if isinstance(desc, dict):
                # If it's ADF (API v3), just stringify or extract text. 
                # We'll just safely stringify for now.
                desc = json.dumps(desc)
                
            tickets.append({
                "id": issue.get("key"),
                "title": fields.get("summary", ""),
                "description": desc,
                "type": fields.get("issuetype", {}).get("name", "Task"),
                "status": fields.get("status", {}).get("name", "To Do")
            })
            
        return {"tickets": tickets}
        
    except urllib.error.HTTPError as e:
        try:
            error_msg = e.read().decode("utf-8")
        except:
            error_msg = str(e)
        # Always return 400 so we can surface the message clearly to the UI
        # without triggering confusing generic 410/500 errors in the browser console
        raise HTTPException(status_code=400, detail=f"Jira API Error ({e.code}): {error_msg}. URL hit: {full_url}")
    except urllib.error.URLError as e:
        raise HTTPException(status_code=400, detail=f"Failed to reach Jira Server: {str(e.reason)}. URL hit: {full_url}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

