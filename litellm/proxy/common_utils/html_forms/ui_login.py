import os

from litellm.proxy.utils import get_custom_url

url_to_redirect_to = os.getenv("PROXY_BASE_URL", "")
server_root_path = os.getenv("SERVER_ROOT_PATH", "")
if server_root_path != "":
    url_to_redirect_to += server_root_path
url_to_redirect_to += "/login"
new_ui_login_url = get_custom_url("", "ui/login")


def build_ui_login_form(
    show_deprecation_banner: bool = False,
    hide_default_credentials_hint: bool = False,
    base_url: str = "",
) -> str:
    feishu_app_id = os.getenv("FEISHU_APP_ID", "")
    feishu_login_url = (
        f"https://open.feishu.cn/open-apis/authen/v1/index"
        f"?redirect_uri={base_url}sso/feishu/callback"
        f"&app_id={feishu_app_id}"
    ) if feishu_app_id else ""
    banner_html = (
        f"""
        <div class="deprecation-banner">
            <strong>Deprecated:</strong> Logging in with username and password on this page is deprecated.
            Please use the <a href="{new_ui_login_url}">new login page</a> instead.
            This page will be dedicated to signing in via SSO in the future.
        </div>
        """
        if show_deprecation_banner
        else ""
    )

    # LITELLM-UI-001: 默认凭据提示 → 替换为三个飞书配置教程链接
    # （URL 与登录后首页顶部 GuideButtons 一致，fjdynamics 飞书 wiki）
    info_box_html = (
        ""
        if hide_default_credentials_hint
        else """
        <div class="info-box guide-box">
            <div class="info-header">
                使用指南 & 配置教程
            </div>
            <div class="guide-links">
                <a href="https://fjdynamics.feishu.cn/wiki/FE5awqnh8i8p0Ak9G8jc6xpPnjd?from=from_copylink" target="_blank" rel="noopener noreferrer" class="guide-link">
                    <span class="guide-dot" style="background:#3B82F6"></span>LiteLLM 使用指南
                </a>
                <a href="https://fjdynamics.feishu.cn/wiki/Lul8wmoCki6NqYkCf9fcsr0gnBh?from=from_copylink" target="_blank" rel="noopener noreferrer" class="guide-link">
                    <span class="guide-dot" style="background:#D97757"></span>Claude 配置教程
                </a>
                <a href="https://fjdynamics.feishu.cn/wiki/AaWawVDUziMxJXkmeh0cA8dYnmx?from=from_copylink" target="_blank" rel="noopener noreferrer" class="guide-link">
                    <span class="guide-dot" style="background:#10A37F"></span>Codex 配置教程
                </a>
                <a href="https://fjdynamics.feishu.cn/wiki/Ltyaw1xIPiPa70kGoJGc5baOnGb?from=from_copylink" target="_blank" rel="noopener noreferrer" class="guide-link">
                    <span class="guide-dot" style="background:#7C3AED"></span>Workbuddy 配置教程
                </a>
            </div>
        </div>
        """
    )

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>LiteLLM Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: #f8fafc;
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            color: #333;
        }}

        form {{
            background-color: #fff;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            width: 450px;
            max-width: 100%;
        }}
        
        .logo-container {{
            text-align: center;
            margin-bottom: 30px;
        }}
        
        .logo {{
            font-size: 24px;
            font-weight: 600;
            color: #1e293b;
        }}
        
        h2 {{
            margin: 0 0 10px;
            color: #1e293b;
            font-size: 28px;
            font-weight: 600;
            text-align: center;
        }}
        
        .subtitle {{
            color: #64748b;
            margin: 0 0 20px;
            font-size: 16px;
            text-align: center;
        }}

        .info-box {{
            background-color: #f1f5f9;
            border-radius: 6px;
            padding: 20px;
            margin-bottom: 30px;
            border-left: 4px solid #2563eb;
        }}
        
        .info-header {{
            display: flex;
            align-items: center;
            margin-bottom: 12px;
            color: #1e40af;
            font-weight: 600;
            font-size: 16px;
        }}
        
        .info-header svg {{
            margin-right: 8px;
        }}
        
        .info-box p {{
            color: #475569;
            margin: 8px 0;
            line-height: 1.5;
            font-size: 14px;
        }}

        .guide-links {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin-top: 12px;
        }}

        .guide-link {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 9px 12px;
            border-radius: 6px;
            background-color: #fff;
            border: 1px solid #e2e8f0;
            color: #334155;
            font-size: 14px;
            font-weight: 500;
            text-decoration: none;
            transition: border-color 0.15s, box-shadow 0.15s, transform 0.1s;
        }}

        .guide-link:hover {{
            border-color: #94a3b8;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
            transform: translateY(-1px);
            text-decoration: none;
        }}

        .guide-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            flex-shrink: 0;
        }}

        label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #334155;
            font-size: 14px;
        }}
        
        .required {{
            color: #dc2626;
            margin-left: 2px;
        }}

        input[type="text"],
        input[type="password"] {{
            width: 100%;
            padding: 10px 14px;
            margin-bottom: 20px;
            box-sizing: border-box;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            font-size: 15px;
            color: #1e293b;
            background-color: #fff;
            transition: border-color 0.2s, box-shadow 0.2s;
        }}
        
        input[type="text"]:focus,
        input[type="password"]:focus {{
            outline: none;
            border-color: #3b82f6;
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
        }}

        .toggle-password {{
            display: flex;
            align-items: center;
            margin-top: -15px;
            margin-bottom: 20px;
        }}
        
        .toggle-password input[type="checkbox"] {{
            margin-right: 8px;
            vertical-align: middle;
            width: 16px;
            height: 16px;
        }}
        
        .toggle-password label {{
            margin-bottom: 0;
            font-size: 14px;
            cursor: pointer;
            line-height: 1;
        }}

        input[type="submit"] {{
            background-color: #6466E9;
            color: #fff;
            cursor: pointer;
            font-weight: 500;
            border: none;
            padding: 10px 16px;
            transition: background-color 0.2s;
            border-radius: 6px;
            margin-top: 10px;
            font-size: 14px;
            width: 100%;
        }}

        input[type="submit"]:hover {{
            background-color: #4138C2;
        }}
        
        a {{
            color: #3b82f6;
            text-decoration: none;
        }}

        a:hover {{
            text-decoration: underline;
        }}
        
        code {{
            background-color: #f1f5f9;
            padding: 2px 4px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 13px;
            color: #334155;
        }}
        
        .help-text {{
            color: #64748b;
            font-size: 14px;
            margin-top: -12px;
            margin-bottom: 20px;
        }}

        .sso-section {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
        }}

        .sso-button {{
            display: block;
            padding: 12px 16px;
            background-color: #3370ff;
            color: #fff;
            text-align: center;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            transition: background-color 0.2s;
            margin-top: 10px;
        }}

        .sso-button:hover {{
            background-color: #2856c6;
            text-decoration: none;
        }}

        .sso-button svg {{
            vertical-align: middle;
            margin-right: 8px;
        }}


        .deprecation-banner {{
            background-color: #fee2e2;
            border: 1px solid #ef4444;
            color: #991b1b;
            padding: 14px 16px;
            border-radius: 6px;
            margin-bottom: 20px;
            font-size: 14px;
            line-height: 1.5;
        }}

        .deprecation-banner a {{
            color: #991b1b;
            font-weight: 600;
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <form action="{url_to_redirect_to}" method="post">
        {banner_html}
        <div class="logo-container">
            <div class="logo">
                🚅 LiteLLM
            </div>
        </div>
        <h2>Login</h2>
        {info_box_html}
        <label for="username">Username<span class="required">*</span></label>
        <input type="text" id="username" name="username" required placeholder="Enter your username" autocomplete="username">
        
        <label for="password">Password<span class="required">*</span></label>
        <input type="password" id="password" name="password" required placeholder="Enter your password" autocomplete="current-password">
        <div class="toggle-password">
            <input type="checkbox" id="show-password" onclick="togglePasswordVisibility()">
            <label for="show-password">Show password</label>
        </div>
        <input type="submit" value="Login">
        <div class="sso-section">
            <a href="{feishu_login_url}" class="sso-button">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
                </svg>
                通过飞书登录
            </a>
        </div>
    </form>
    <script>
        function togglePasswordVisibility() {{
            var passwordField = document.getElementById("password");
            passwordField.type = passwordField.type === "password" ? "text" : "password";
        }}
    </script>
</body>
</html>
"""
