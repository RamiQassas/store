import os

def fix_file():
    with open('apps/site/views.py', 'rb') as f:
        data = f.read()

    # Find the clean part:
    good_text = b'@support_required\ndef control_send_notification(request): return render(request, "site/control_notification_form.html")\n'
    idx = data.find(good_text)
    if idx == -1:
        good_text = b'@support_required\r\ndef control_send_notification(request): return render(request, "site/control_notification_form.html")\r\n'
        idx = data.find(good_text)

    if idx != -1:
        good_data = data[:idx + len(good_text)]
        with open('apps/site/views.py', 'wb') as f:
            f.write(good_data)
        print('Fixed file')
    else:
        print('Not found')

if __name__ == '__main__':
    fix_file()
