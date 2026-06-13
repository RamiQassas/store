import sys

content = open('apps/site/views.py', 'r', encoding='utf-8').read()
start_marker = 'def send_financial_notification(user, title, body, action_url="/dashboard/wallet/"):\n'
end_marker = '    except: pass\n'

start_idx = content.find(start_marker)
if start_idx != -1:
    end_idx = content.find(end_marker, start_idx)
    if end_idx != -1:
        end_idx += len(end_marker)
        
        new_fn = """def send_financial_notification(user, title, body, action_url="/dashboard/wallet/"):
    # Rely entirely on notify_user which now natively handles in-app, push, and email based on user preferences.
    try:
        notify_user(user=user, title=title, body=body, action_url=action_url, category='financial', priority="high")
    except Exception as e:
        pass\n"""
        
        new_content = content[:start_idx] + new_fn + content[end_idx:]
        open('apps/site/views.py', 'w', encoding='utf-8').write(new_content)
        print("Success")
    else:
        print("End marker not found")
else:
    print("Start marker not found")
