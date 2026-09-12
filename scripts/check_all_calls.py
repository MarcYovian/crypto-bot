import ast
import os
import sys
import inspect
import importlib

sys.path.insert(0, os.path.abspath("backend"))

import src.repository as repos
from src.repository.base import BaseRepository
import src.services as services
import src.clients as clients

classes_dict = {}

def register_module_classes(mod):
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if isinstance(attr, type):
            methods = {m: getattr(attr, m) for m in dir(attr) if not m.startswith("__")}
            classes_dict[attr_name.lower()] = (attr_name, methods, attr)

register_module_classes(repos)
register_module_classes(services)
register_module_classes(clients)

print(f"Loaded {len(classes_dict)} classes for verification.")

issues = []

for root, dirs, files in os.walk("backend/src"):
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, "backend")
            with open(filepath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=filepath)

            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    caller = node.func.value
                    method_name = node.func.attr
                    
                    caller_name = ""
                    if isinstance(caller, ast.Attribute):
                        caller_name = caller.attr
                    elif isinstance(caller, ast.Name):
                        caller_name = caller.id

                    if not caller_name:
                        continue
                    
                    # Normalize name
                    norm = caller_name.replace("_", "").lower()
                    
                    matched_cls = None
                    for key, (c_name, c_methods, c_cls) in classes_dict.items():
                        k_norm = key.replace("_", "").lower()
                        if k_norm == norm or k_norm == norm + "service" or k_norm == norm + "client" or k_norm == norm + "repository":
                            matched_cls = (c_name, c_methods, c_cls)
                            break
                        # e.g. trade_repo -> traderepository
                        if "repo" in norm and norm.replace("repo", "repository") == k_norm:
                            matched_cls = (c_name, c_methods, c_cls)
                            break
                        # e.g. binance_client -> binancerestclient
                        if "binance_client" == caller_name and "binancerestclient" == k_norm:
                            matched_cls = (c_name, c_methods, c_cls)
                            break
                        # e.g. telegram_client -> telegramnotifierclient
                        if "telegram_client" == caller_name and "telegramnotifierclient" == k_norm:
                            matched_cls = (c_name, c_methods, c_cls)
                            break
                        # e.g. risk_calculator / risk_calc -> riskcalculatorservice
                        if norm in ("riskcalc", "riskcalculator") and "riskcalculatorservice" == k_norm:
                            matched_cls = (c_name, c_methods, c_cls)
                            break
                        # e.g. signal_parser -> signalparserservice
                        if norm == "signalparser" and "signalparserservice" == k_norm:
                            matched_cls = (c_name, c_methods, c_cls)
                            break
                        # e.g. precision_service / precision_filter -> precisionfilterservice
                        if norm in ("precisionservice", "precisionfilter") and "precisionfilterservice" == k_norm:
                            matched_cls = (c_name, c_methods, c_cls)
                            break
                        # e.g. inst_service / instrument_service -> instrumentservice
                        if norm in ("instservice", "instrumentservice") and "instrumentservice" == k_norm:
                            matched_cls = (c_name, c_methods, c_cls)
                            break

                    if matched_cls:
                        c_name, c_methods, c_cls = matched_cls
                        if method_name not in c_methods:
                            issues.append(f"[UNKNOWN METHOD] {rel_path}:{node.lineno} - {caller_name}.{method_name}() does not exist on {c_name}")
                        else:
                            meth = c_methods[method_name]
                            if inspect.isfunction(meth) or inspect.ismethod(meth) or inspect.iscoroutinefunction(meth):
                                try:
                                    sig = inspect.signature(meth)
                                    param_names = [p for p in sig.parameters.keys() if p != 'self']
                                    has_var_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                                    if not has_var_kwargs:
                                        for kw in node.keywords:
                                            if kw.arg and kw.arg not in param_names:
                                                issues.append(f"[INVALID KWARG] {rel_path}:{node.lineno} - {caller_name}.{method_name}() invalid keyword '{kw.arg}'. Expected: {param_names}")
                                except (ValueError, TypeError):
                                    pass

for issue in issues:
    print(issue)
