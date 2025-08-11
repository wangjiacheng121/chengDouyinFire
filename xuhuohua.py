# 抖音自动续火花工具 - GitHub Actions 适配版
# 自动发送抖音私信给指定联系人，保持互动关系不断

import time
import os
import json
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import pickle

# 用户配置文件路径
USER_CONFIG_PATH = "xuhuohua_users.json"

# 多用户配置 - 通过环境变量注入
# 每个用户需要设置: 
# - name: 用户名称(用于区分不同用户)
# - contacts: 联系人列表
# - message: 要发送的消息
# - cookie_path: cookie保存路径
USERS = []
ACTIVE_USER_INDEX = 0  # 当前活跃用户索引

def load_user_config():
    """从环境变量加载用户配置"""
    global USERS, ACTIVE_USER_INDEX
    
    try:
        config_json = os.environ.get("USER_CONFIG_JSON")
        if not config_json:
            print("未找到USER_CONFIG_JSON环境变量")
            return False
            
        config = json.loads(config_json)
        
        if "users" in config and isinstance(config["users"], list) and len(config["users"]) > 0:
            USERS = config["users"]
            print(f"成功加载了 {len(USERS)} 个用户配置")
            
            if "active_user_index" in config and isinstance(config["active_user_index"], int):
                if 0 <= config["active_user_index"] < len(USERS):
                    ACTIVE_USER_INDEX = config["active_user_index"]
                else:
                    ACTIVE_USER_INDEX = 0
            return True
        else:
            print("USER_CONFIG_JSON格式错误")
            return False
    except Exception as e:
        print(f"加载用户配置失败: {e}")
        traceback.print_exc()
        return False

def get_active_user():
    """获取当前活跃用户的配置"""
    if 0 <= ACTIVE_USER_INDEX < len(USERS):
        return USERS[ACTIVE_USER_INDEX]
    else:
        raise ValueError("无效的用户索引")

def save_cookies(driver, path):
    """保存cookies到文件"""
    cookies_dir = os.path.dirname(path)
    if cookies_dir and not os.path.exists(cookies_dir):
        os.makedirs(cookies_dir)
        
    with open(path, "wb") as f:
        pickle.dump(driver.get_cookies(), f)

def load_cookies_from_var(driver, cookie_str):
    """从环境变量字符串加载cookies"""
    try:
        if not cookie_str:
            print("DOUYIN_COOKIE环境变量为空")
            return False
            
        cookies = json.loads(cookie_str)
        if not cookies:
            print("Cookie内容为空")
            return False
            
        for cookie in cookies:
            try:
                # 过滤掉无效的cookie属性
                if 'expiry' in cookie and isinstance(cookie['expiry'], float):
                    cookie['expiry'] = int(cookie['expiry'])
                driver.add_cookie(cookie)
            except Exception as e:
                print(f"添加单个cookie时出错: {e}")
        return True
    except Exception as e:
        print(f"加载cookie过程中出现异常: {e}")
        traceback.print_exc()
        return False

def take_screenshots(driver, name, user_name=None):
    """保存当前页面截图，便于调试"""
    try:
        if user_name:
            # 如果提供了用户名，则保存到用户专属文件夹
            directory = f"screenshots/{user_name}"
            if not os.path.exists(directory):
                os.makedirs(directory)
            screenshot_path = f"{directory}/douyin_{name}.png"
        else:
            # 否则保存到默认位置
            screenshot_path = f"douyin_{name}.png"
            
        driver.save_screenshot(screenshot_path)
        print(f"已保存截图: {screenshot_path}")
        return screenshot_path
    except Exception as e:
        print(f"保存截图失败: {e}")
        return None

def init_driver(user_config):
    """初始化无头浏览器并使用环境变量中的cookie登录"""
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--headless=new")  # 启用无头模式
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    try:
        print(f"正在为用户 [{user_config['name']}] 初始化Chrome浏览器...")
        driver_path = ChromeDriverManager().install()
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print("Chrome浏览器初始化成功")
    except Exception as e:
        print(f"Chrome浏览器初始化失败: {e}")
        raise

    try:
        print("正在访问抖音网站...")
        driver.get("https://www.douyin.com/")
        print("成功加载抖音网站")
        time.sleep(2)
        
        # 从环境变量加载cookie
        cookie_str = os.environ.get("DOUYIN_COOKIE")
        if not cookie_str:
            raise ValueError("未找到DOUYIN_COOKIE环境变量")
            
        print("尝试加载cookie...")
        if load_cookies_from_var(driver, cookie_str):
            driver.refresh()
            print("已加载cookie并刷新页面")
            time.sleep(3)
            # 验证登录状态
            try:
                # 检查是否有登录状态的元素
                profile_elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'avatar') or contains(@class, 'profile')]")
                if profile_elements and any(e.is_displayed() for e in profile_elements):
                    print("登录状态验证成功")
                else:
                    print("警告: 可能没有正确登录")
                    take_screenshots(driver, "login_status", user_config['name'])
            except Exception as e:
                print(f"登录状态验证出错: {e}")
                take_screenshots(driver, "login_error", user_config['name'])
        else:
            raise RuntimeError("加载cookie失败")
            
        return driver
    except Exception as e:
        print(f"访问抖音网站失败: {e}")
        driver.quit()
        traceback.print_exc()
        raise

def send_message_to_contact(driver, contact_name, message, user_config):
    """为指定联系人发送消息"""
    user_name = user_config["name"]
    
    try:
        # 访问抖音首页
        driver.get("https://www.douyin.com/")
        time.sleep(5)
        take_screenshots(driver, "home", user_name)
        
        # 查找私信按钮 - 使用data-e2e属性定位
        try:
            message_button = driver.find_element(By.XPATH, "//a[@data-e2e='messaging-icon']")
            print("找到私信按钮")
            message_button.click()
            print("已点击私信按钮")
            time.sleep(3)
            take_screenshots(driver, "after_click_message_icon", user_name)
        except NoSuchElementException:
            try:
                # 备选选择器
                message_button = driver.find_element(By.XPATH, "//div[contains(@class, 'message-icon')]")
                print("找到私信按钮(备选选择器)")
                message_button.click()
                print("已点击私信按钮")
                time.sleep(3)
                take_screenshots(driver, "after_click_message_icon", user_name)
            except Exception as e:
                print(f"点击私信按钮失败: {e}")
                take_screenshots(driver, "message_button_error", user_name)
                return False
        
        # 查找联系人
        print(f"查找联系人: {contact_name}")
        time.sleep(2)
        
        # 联系人选择器
        contact_selectors = [
            f"//div[contains(text(), '{contact_name}')]",
            f"//span[contains(text(), '{contact_name}')]",
            f"//div[contains(., '{contact_name}')]"
        ]
        
        contact_element = None
        for selector in contact_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        print(f"找到联系人: {contact_name}")
                        contact_element = element
                        break
                if contact_element:
                    break
            except:
                continue
        
        if not contact_element:
            print(f"未找到联系人: {contact_name}")
            take_screenshots(driver, "contact_not_found", user_name)
            return False
        
        # 点击联系人
        try:
            print(f"点击联系人: {contact_name}")
            driver.execute_script("arguments[0].click();", contact_element)
            time.sleep(3)
            take_screenshots(driver, "after_click_contact", user_name)
        except Exception as e:
            print(f"点击联系人失败: {e}")
            take_screenshots(driver, "contact_click_error", user_name)
            return False
        
        # 查找输入框
        input_element = None
        input_selectors = [
            "//textarea",
            "//div[@contenteditable='true']"
        ]
        
        for selector in input_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        input_element = element
                        print("找到输入框")
                        break
                if input_element:
                    break
            except:
                continue
        
        if not input_element:
            print("未找到输入框")
            take_screenshots(driver, "input_not_found", user_name)
            return False
        
        # 输入消息
        try:
            input_element.clear()
            input_element.send_keys(message)
            time.sleep(1)
            print(f"已输入消息: {message}")
            take_screenshots(driver, "after_input_message", user_name)
        except Exception as e:
            print(f"输入消息失败: {e}")
            take_screenshots(driver, "input_error", user_name)
            return False
        
        # 发送消息(回车键)
        try:
            # 确保输入框有焦点
            input_element.click()
            time.sleep(0.5)
            
            # 使用回车键发送
            print("按回车键发送消息")
            input_element.send_keys('\n')
            time.sleep(1)
            take_screenshots(driver, "after_send", user_name)
            print(f"成功发送消息: {message}")
            return True
        except Exception as e:
            print(f"发送消息失败: {e}")
            take_screenshots(driver, "send_error", user_name)
            return False
            
    except Exception as e:
        print(f"发送消息失败: {e}")
        traceback.print_exc()
        take_screenshots(driver, "send_message_error", user_name)
        return False

def send_messages_for_user(user_config):
    """为指定用户发送所有消息"""
    try:
        user_name = user_config["name"]
        contacts = user_config["contacts"]
        message = user_config["message"]
        
        print(f"开始为用户 [{user_name}] 发送消息...")
        driver = init_driver(user_config)
        
        success_count = 0
        for contact in contacts:
            print(f"向 {contact} 发送消息...")
            result = send_message_to_contact(driver, contact, message, user_config)
            if result:
                print(f"向 {contact} 发送消息成功")
                success_count += 1
            else:
                print(f"向 {contact} 发送消息失败")
            time.sleep(3)
        
        driver.quit()
        print(f"用户 [{user_name}] 消息发送完毕！成功: {success_count}/{len(contacts)}")
        return success_count > 0
        
    except Exception as e:
        print(f"发送消息过程中发生错误: {e}")
        traceback.print_exc()
        try:
            driver.quit()
        except:
            pass
        return False

def send_messages_for_all_users():
    """为所有配置的用户执行续火花操作"""
    print("\n" + "="*50)
    print(f"开始为所有用户执行续火花操作 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    if not USERS:
        print("未配置任何用户，请检查环境变量")
        return False
    
    total_users = len(USERS)
    success_users = 0
    
    for i, user in enumerate(USERS):
        user_name = user["name"]
        print(f"\n[{i+1}/{total_users}] 正在为用户 [{user_name}] 执行续火花操作...")
        
        try:
            result = send_messages_for_user(user)
            if result:
                success_users += 1
                print(f"用户 [{user_name}] 续火花操作成功")
            else:
                print(f"用户 [{user_name}] 续火花操作失败")
        except Exception as e:
            print(f"用户 [{user_name}] 执行过程中出错: {e}")
            traceback.print_exc()
        
        # 如果不是最后一个用户，等待一段时间再执行下一个用户
        if i < total_users - 1:
            wait_time = 30  # 用户之间的等待时间，单位秒
            print(f"等待 {wait_time} 秒后执行下一个用户...")
            time.sleep(wait_time)
    
    print("\n" + "="*50)
    print(f"所有用户续火花操作完成: 成功 {success_users}/{total_users}")
    print(f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    return success_users > 0

def main():
    """主函数 - 适配GitHub Actions环境"""
    print(f"开始执行续火花任务 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 加载用户配置
    if not load_user_config():
        print("用户配置加载失败，任务终止")
        return
    
    # 执行任务
    result = send_messages_for_all_users()
    
    print(f"任务{'完成' if result else '失败'} - {time.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
