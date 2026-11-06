from __future__ import annotations

from .config import settings


def _param(name: str, location: str, schema_type: str = "string", required: bool = False) -> dict:
    return {
        "name": name,
        "in": location,
        "required": required,
        "schema": {"type": schema_type},
    }


def build_openapi_document() -> dict:
    """Return the OpenAPI document for the legacy-compatible HTTP API."""
    paths = {
        "/Account/Login": {
            "post": {
                "tags": ["Account"],
                "summary": "Login",
                "parameters": [_param("dryRun", "query", "boolean")],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/User"}}}},
                "responses": {"200": {"description": "Success"}, "400": {"description": "Bad Request"}},
            }
        },
        "/Account/Users": {
            "get": {
                "tags": ["Account"],
                "summary": "Read users",
                "parameters": [_param("email", "query")],
                "responses": {"200": {"description": "Success"}, "401": {"description": "Unauthorized"}},
            },
            "put": {
                "tags": ["Account"],
                "summary": "Update user",
                "parameters": [_param("changePassphrase", "query", "boolean")],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/User"}}}},
                "responses": {"200": {"description": "Success"}},
            },
            "delete": {
                "tags": ["Account"],
                "summary": "Delete user",
                "parameters": [_param("email", "query", required=True)],
                "responses": {"200": {"description": "Success"}},
            },
        },
        "/Account/Users/Assignable": {
            "get": {"tags": ["Account"], "summary": "Read assignable users", "responses": {"200": {"description": "Success"}}}
        },
        "/Inspection/types": {
            "get": {"tags": ["Inspection"], "summary": "Read inspection types", "responses": {"200": {"description": "Success"}}}
        },
        "/Inspection/renovationtypes": {
            "get": {"tags": ["Inspection"], "summary": "Read renovation types", "responses": {"200": {"description": "Success"}}}
        },
        "/Inspection": {
            "post": {
                "tags": ["Inspection"],
                "summary": "Save inspection reports",
                "parameters": [_param("dryRun", "query", "boolean")],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "array", "items": {"$ref": "#/components/schemas/InspectionReport"}}}}},
                "responses": {"200": {"description": "Success"}},
            }
        },
        "/Collections/Playgrounds/Items/": {
            "get": {"tags": ["Playground"], "summary": "Read playground feature collection", "responses": {"200": {"description": "Success"}}}
        },
        "/Collections/Playgrounds/Items/{uuid}": {
            "get": {
                "tags": ["Playground"],
                "summary": "Read playground as feature",
                "parameters": [_param("uuid", "path", required=True)],
                "responses": {"200": {"description": "Success"}},
            }
        },
        "/Playground/{id}": {
            "get": {
                "tags": ["Playground"],
                "summary": "Read playground by id",
                "parameters": [
                    _param("id", "path", "integer", True),
                    _param("inspectionType", "query"),
                    _param("withDefects", "query", "boolean"),
                    _param("withInspections", "query", "boolean"),
                ],
                "responses": {"200": {"description": "Success"}},
            }
        },
        "/Playground/byplaydevice/{playdeviceFid}": {
            "get": {
                "tags": ["Playground"],
                "summary": "Read playground by playdevice",
                "parameters": [_param("playdeviceFid", "path", "integer", True)],
                "responses": {"200": {"description": "Success"}},
            }
        },
        "/Playground/byname": {
            "get": {
                "tags": ["Playground"],
                "summary": "Read playground by name",
                "parameters": [
                    _param("name", "query", required=True),
                    _param("inspectionType", "query"),
                    _param("withDefects", "query", "boolean"),
                    _param("withInspections", "query", "boolean"),
                ],
                "responses": {"200": {"description": "Success"}},
            }
        },
        "/Playground/onlynames": {
            "get": {
                "tags": ["Playground"],
                "summary": "Read playground names",
                "parameters": [_param("inspectionType", "query")],
                "responses": {"200": {"description": "Success"}},
            }
        },
        "/Playground/mapimage": {
            "get": {
                "tags": ["Playground"],
                "summary": "Read map image URL",
                "parameters": [_param("x", "query", "number", True), _param("y", "query", "number", True)],
                "responses": {"200": {"description": "Success"}},
            }
        },
        "/Playdevice": {
            "post": {
                "tags": ["Playdevice"],
                "summary": "Save playdevice",
                "parameters": [_param("dryRun", "query", "boolean")],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
                "responses": {"200": {"description": "Success"}},
            },
            "put": {
                "tags": ["Playdevice"],
                "summary": "Exchange playdevice image",
                "parameters": [_param("fid", "query", "integer", True), _param("dryRun", "query", "boolean")],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
                "responses": {"200": {"description": "Success"}},
            },
        },
        "/Playdevice/{playdeviceFid}/Picture": {
            "get": {
                "tags": ["Playdevice"],
                "summary": "Read playdevice picture",
                "parameters": [_param("playdeviceFid", "path", "integer", True), _param("dryRun", "query", "boolean")],
                "responses": {"200": {"description": "Success"}},
            },
            "put": {
                "tags": ["Playdevice"],
                "summary": "Write playdevice picture",
                "parameters": [_param("playdeviceFid", "path", "integer", True), _param("dryRun", "query", "boolean")],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
                "responses": {"200": {"description": "Success"}},
            },
        },
        "/Defect": {
            "get": {
                "tags": ["Defect"],
                "summary": "Read defect",
                "parameters": [_param("tid", "query", "integer", True)],
                "responses": {"200": {"description": "Success"}},
            },
            "post": {
                "tags": ["Defect"],
                "summary": "Update defect",
                "parameters": [_param("dryRun", "query", "boolean")],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Defect"}}}},
                "responses": {"200": {"description": "Success"}},
            },
            "put": {
                "tags": ["Defect"],
                "summary": "Create defect",
                "parameters": [_param("dryRun", "query", "boolean")],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Defect"}}}},
                "responses": {"200": {"description": "Success"}},
            },
        },
        "/Defect/{tid}/send-mail": {
            "post": {
                "tags": ["Defect"],
                "summary": "Send defect info mail via local SMTP",
                "parameters": [_param("tid", "path", "integer", True), _param("dryRun", "query", "boolean")],
                "responses": {"200": {"description": "Success"}},
            }
        },
        "/Defect/{tid}/accept": {
            "post": {
                "tags": ["Defect"],
                "summary": "Accept defect assignment",
                "parameters": [_param("tid", "path", "integer", True), _param("dryRun", "query", "boolean")],
                "responses": {"200": {"description": "Success"}},
            }
        },
        "/Defect/{tid}/reject": {
            "post": {
                "tags": ["Defect"],
                "summary": "Reject defect assignment",
                "parameters": [_param("tid", "path", "integer", True), _param("dryRun", "query", "boolean")],
                "responses": {"200": {"description": "Success"}},
            }
        },
        "/Defect/Picture/{tid}": {
            "get": {
                "tags": ["Defect"],
                "summary": "Read defect pictures",
                "parameters": [_param("tid", "path", "integer", True), _param("thumb", "query", "boolean"), _param("dryRun", "query", "boolean")],
                "responses": {"200": {"description": "Success"}},
            },
            "put": {
                "tags": ["Defect"],
                "summary": "Write defect picture",
                "parameters": [_param("tid", "path", "integer", True), _param("dryRun", "query", "boolean")],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
                "responses": {"200": {"description": "Success"}},
            },
        },
        "/Document": {
            "post": {
                "tags": ["Document"],
                "summary": "Upload document (administrator)",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
                "responses": {"200": {"description": "Success"}, "401": {"description": "Unauthorized"}},
            }
        },
        "/Document/{documentfid}": {
            "get": {
                "tags": ["Document"],
                "summary": "Read document",
                "parameters": [_param("documentfid", "path", "integer", True), _param("type", "query", required=True)],
                "responses": {"200": {"description": "Success"}},
            },
            "delete": {
                "tags": ["Document"],
                "summary": "Delete document (administrator)",
                "parameters": [_param("documentfid", "path", "integer", True), _param("type", "query", required=True)],
                "responses": {"200": {"description": "Success"}, "401": {"description": "Unauthorized"}, "404": {"description": "Not found"}},
            },
        },
        "/Document/{documentfid}/Name": {
            "put": {
                "tags": ["Document"],
                "summary": "Rename document (administrator)",
                "parameters": [_param("documentfid", "path", "integer", True), _param("type", "query", required=True)],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
                "responses": {"200": {"description": "Success"}, "401": {"description": "Unauthorized"}},
            }
        },
        "/PushSubscription/Register": {
            "post": {
                "tags": ["PushSubscription"],
                "summary": "Register push subscription",
                "parameters": [_param("dryRun", "query", "boolean")],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
                "responses": {"200": {"description": "Success"}},
            }
        },
        "/PushSubscription/Unregister": {
            "delete": {
                "tags": ["PushSubscription"],
                "summary": "Unregister push subscription",
                "parameters": [_param("dryRun", "query", "boolean")],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
                "responses": {"200": {"description": "Success"}},
            }
        },
        "/PushSubscription/Me": {
            "get": {
                "tags": ["PushSubscription"],
                "summary": "Read own push subscriptions",
                "parameters": [_param("dryRun", "query", "boolean")],
                "responses": {"200": {"description": "Success"}},
            }
        },
    }

    document = {
        "openapi": "3.0.1",
        "info": {
            "title": "Winterthur Playground Regular Inspection API - V1",
            "version": "v1",
            "description": settings.service_description,
        },
        "paths": paths,
        "components": {
            "schemas": {
                "User": {"type": "object", "additionalProperties": True},
                "InspectionReport": {"type": "object", "additionalProperties": True},
                "Defect": {"type": "object", "additionalProperties": True},
            }
        },
    }
    if settings.token_issuer:
        document["servers"] = [{"url": settings.token_issuer.rstrip("/")}]
    return document


def swagger_ui_html(base_path: str = "") -> str:
    json_url = f"{base_path}/swagger/v1/swagger.json" or "/swagger/v1/swagger.json"
    return f"""<!doctype html>
<html lang=\"de\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Winterthur Playground Regular Inspection API - V1</title>
<style>
body{{margin:0;font:14px Arial,sans-serif;color:#3b4151;background:#fafafa}}header{{background:#1b1b1b;color:white;padding:18px 24px}}main{{max-width:1100px;margin:24px auto;padding:0 18px}}h1{{font-size:24px;margin:0}}.desc{{margin-top:6px;color:#ddd}}.toolbar{{margin:18px 0}}a{{color:#3b82f6}}.tag{{margin:24px 0}}.op{{background:white;border:1px solid #ddd;border-radius:4px;margin:8px 0;padding:10px 12px}}.method{{display:inline-block;min-width:58px;font-weight:bold;text-transform:uppercase}}.path{{font-family:monospace;font-weight:bold}}.summary{{margin-left:12px;color:#555}}.get .method{{color:#0f6ab4}}.post .method{{color:#49cc90}}.put .method{{color:#fca130}}.delete .method{{color:#f93e3e}}.loading{{padding:20px;background:white;border:1px solid #ddd}}
</style>
</head>
<body>
<header><h1>Winterthur Playground Regular Inspection API - V1</h1><div class=\"desc\">Swagger / OpenAPI V1</div></header>
<main><div class=\"toolbar\"><a href=\"{json_url}\">OpenAPI JSON</a></div><div id=\"api\" class=\"loading\">API-Beschreibung wird geladen ...</div></main>
<script>
fetch({json_url!r}).then(r=>r.json()).then(doc=>{{
  const grouped={{}};
  Object.entries(doc.paths||{{}}).forEach(([path,ops])=>Object.entries(ops).forEach(([method,op])=>{{
    const tag=(op.tags&&op.tags[0])||'API'; (grouped[tag]??=[]).push({{path,method,op}});
  }}));
  const root=document.getElementById('api'); root.className=''; root.innerHTML='';
  Object.entries(grouped).forEach(([tag,ops])=>{{
    const section=document.createElement('section'); section.className='tag';
    section.innerHTML='<h2>'+tag+'</h2>';
    ops.forEach(x=>{{ const div=document.createElement('div'); div.className='op '+x.method;
      div.innerHTML='<span class=\"method\">'+x.method+'</span><span class=\"path\">'+x.path+'</span><span class=\"summary\">'+(x.op.summary||'')+'</span>'; section.appendChild(div); }});
    root.appendChild(section);
  }});
}}).catch(err=>{{document.getElementById('api').textContent='OpenAPI-Beschreibung konnte nicht geladen werden: '+err;}});
</script>
</body></html>"""
