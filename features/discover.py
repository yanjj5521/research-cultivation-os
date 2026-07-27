from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


def register_discover_routes(app, templates, context: Callable[..., dict[str, Any]]):
    router = APIRouter()

    @router.get('/discover', response_class=HTMLResponse, name='discover_page')
    def discover_page(request: Request, q: str = ''):
        results: list[dict[str, Any]] = []
        error = ''
        query = q.strip()
        if query:
            try:
                params = urllib.parse.urlencode({'search': query, 'per-page': 8, 'sort': 'relevance_score:desc'})
                req = urllib.request.Request(
                    f'https://api.openalex.org/works?{params}',
                    headers={'User-Agent': 'ResearchCultivationOS/2.0 (local research tool)'},
                )
                with urllib.request.urlopen(req, timeout=8) as response:
                    data = json.load(response)
                for item in data.get('results', []):
                    location = item.get('primary_location') or {}
                    source = location.get('source') or {}
                    oa = item.get('open_access') or {}
                    best = item.get('best_oa_location') or {}
                    results.append({
                        'title': item.get('display_name') or '未命名文献',
                        'year': item.get('publication_year') or '',
                        'authors': ', '.join(a.get('author', {}).get('display_name', '') for a in item.get('authorships', [])[:4] if a.get('author')),
                        'source': source.get('display_name') or '',
                        'doi': (item.get('doi') or '').replace('https://doi.org/', ''),
                        'cited_by': item.get('cited_by_count') or 0,
                        'url': best.get('landing_page_url') or best.get('pdf_url') or item.get('doi') or item.get('id'),
                        'open_access': bool(oa.get('is_oa')),
                    })
            except Exception as exc:
                error = f'联网检索暂时不可用：{exc}'
        return templates.TemplateResponse(
            request=request,
            name='discover.html',
            context=context(request, 'discover', q=query, results=results, error=error),
        )

    app.include_router(router)
