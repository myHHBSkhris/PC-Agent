import os, sys, asyncio, shutil, subprocess
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.tools import AgentTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams
from autogen_core.tools import FunctionTool

def need_api_key_and_exit():
    print("\n[SETUP] OPENAI_API_KEY is not set.")
    print("Set it via: Start → 'Environment Variables' → 'Environment Variables…' → New (User)")
    print("  Name: OPENAI_API_KEY   Value: <your key>\nThen reopen PowerShell and run again.\n")
    sys.exit(1)

# ---- Human approval tool ----
def human_confirm(step: str) -> str:
    ans = input(f"\nCONFIRM: {step} [y/N]: ").strip().lower()
    return "yes" if ans in ("y", "yes") else "no"

# ---- WinGet installer tool (silent) ----
def winget_install(package_id: str, silent: bool = True) -> str:
    """
    Install a Windows package by ID using winget.
    Examples: Git.Git, Microsoft.VisualStudioCode
    """
    args = ["winget", "install", "--id", package_id]
    if silent:
        args += ["--silent", "--accept-source-agreements", "--accept-package-agreements"]
    p = subprocess.run(args, capture_output=True, text=True)
    return (p.stdout + p.stderr).strip() or "done"

# ---- VS Code version tool ----
def vscode_get_version() -> str:
    """
    Returns VS Code version (first line of `code --version`), with path fallbacks.
    """
    code_cmd = shutil.which("code")
    candidates = [code_cmd] if code_cmd else []
    candidates += [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
    ]
    for exe in candidates:
        if exe and os.path.exists(exe):
            r = subprocess.run([exe, "--version"], capture_output=True, text=True)
            out = (r.stdout or r.stderr).strip()
            if out:
                return out.splitlines()[0]
    return "unknown"

async def main():
    print("[START] Multi-agent setup…")
    if not os.getenv("OPENAI_API_KEY"):
        need_api_key_and_exit()

    # Disable parallel tool calls for simple, reliable sequencing
    model = OpenAIChatCompletionClient(model="gpt-4o", parallel_tool_calls=False)

    print("[INFO] Starting MCP servers (desktop + web)…")
    desktop_params = StdioServerParams(command="npx", args=["terminator-mcp-agent@latest"])
    web_params     = StdioServerParams(command="npx", args=["@playwright/mcp@latest", "--headless"])

    async with McpWorkbench(desktop_params) as desktop_wb, McpWorkbench(web_params) as web_wb:
        print("[OK] Workbenches connected.")

        desktop_ops = AssistantAgent(
            "desktop_ops",
            model_client=model,
            workbench=desktop_wb,
            system_message=("You control the Windows desktop via MCP. Use reliable accessibility "
                            "selectors (name:/role:). Before any risky change, require human_confirm.")
        )
        web_ops = AssistantAgent(
            "web_ops",
            model_client=model,
            workbench=web_wb,
            system_message=("You handle browsing, downloads, and web forms via MCP. Be explicit and deterministic.")
        )

        # Wrap helper agents so the Supervisor can call them as tools
        desktop_tool = AgentTool(desktop_ops, return_value_as_last_message=True)
        web_tool     = AgentTool(web_ops,     return_value_as_last_message=True)

        # Python function tools (new API)
        human_confirm_tool      = FunctionTool(name="human_confirm",      description="Ask the human to approve a step; returns 'yes' or 'no'.", func=human_confirm)
        winget_install_tool     = FunctionTool(name="winget_install",     description="Install a Windows package via winget by ID (silent by default).", func=winget_install)
        vscode_get_version_tool = FunctionTool(name="vscode_get_version", description="Return the installed Visual Studio Code version.", func=vscode_get_version)

        supervisor = AssistantAgent(
            "supervisor",
            model_client=model,
            tools=[desktop_tool, web_tool, human_confirm_tool, winget_install_tool, vscode_get_version_tool],
            system_message=(
                "You are a careful project manager. Break tasks into steps. "
                "Prefer winget_install(package_id) for silent installs. "
                "Use vscode_get_version() to verify installation. "
                "Use web_ops for browser tasks and desktop_ops for native Windows UI only when needed. "
                "When approval is required, CALL human_confirm(step) and proceed only if it returns 'yes'. "
                "Do NOT ask for confirmation via plain chat."
            ),
            max_tool_iterations=20,
        )

        # --- Mission: silent installs + version check ---
        mission = (
            "Install Git (winget id Git.Git) and Visual Studio Code (winget id Microsoft.VisualStudioCode) "
            "silently using winget_install. Before each install, call human_confirm with a short description. "
            "After installing VS Code, call vscode_get_version() and report the version."
        )
        print("[TASK] ", mission)
        result = await supervisor.run(task=mission)
        print("\n[RESULT]\n", result)

    print("\n[DONE] Crew finished.")

if __name__ == "__main__":
    asyncio.run(main())
