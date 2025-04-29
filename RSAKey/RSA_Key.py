from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import getpass

def generate_rsa_key_pair_with_password():
    # 生成RSA私钥
    private_key = rsa.generate_private_key(
        public_exponent=65537,  # 标准RSA公共指数
        key_size=2048,          # 密钥长度
    )
    
    # 从用户获取密码（不会显示在屏幕上）
    password = getpass.getpass("输入私钥保护密码: ")
    password_confirm = getpass.getpass("确认密码: ")
    
    if password != password_confirm:
        print("密码不匹配！")
        return
    
    if not password:
        print("警告: 没有设置密码，私钥将不受保护")
        encryption_algorithm = serialization.NoEncryption()
    else:
        # 使用密码对私钥进行加密
        encryption_algorithm = serialization.BestAvailableEncryption(password.encode('utf-8'))
    
    # 导出加密的私钥到PEM格式
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption_algorithm  # 使用密码加密
    )
    
    # 导出公钥到PEM格式
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # 将密钥保存到文件
    with open("CUHK_private_key.pem", "wb") as f:
        f.write(private_pem)
    
    with open("CUHK_public_key.pem", "wb") as f:
        f.write(public_pem)
    
    print("RSA密钥对已生成：")
    print(f"- 使用密码保护的私钥已保存到 private_key.pem")
    print(f"- 公钥已保存到 public_key.pem")
    print("重要：请安全保存您的密码，如果丢失将无法使用私钥！")

if __name__ == "__main__":
    generate_rsa_key_pair_with_password()