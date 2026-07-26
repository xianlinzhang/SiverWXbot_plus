from wxautox4.utils.account import get_account_from_process, get_all_accounts

# 获取单个账号
account = get_account_from_process()
print(f"wxid: {account.wxid}")
print(f"data_dir: {account.data_dir}")
print(f"exe_path: {account.exe_path}")
print(f"version: {account.version}")

# 获取所有账号
accounts = get_all_accounts()
for acct in accounts:
    print(f"wxid: {acct.wxid}, data_dir: {acct.data_dir}")