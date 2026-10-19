def should_continue(state: dict) -> str:
    """
    決策節點：判斷 Agent 下一步應該呼叫工具還是結束對話回覆使用者
    """
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else {}
    
    # 判斷是否需要呼叫工具（這裡為模擬邏輯，實際可由 LLM 判斷）
    if "tool_calls" in last_message:
        return "continue_to_tools"
    
    return "end"