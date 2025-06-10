import json

from utils.logger import logger

data_str = """RK=HcXILXlyQ3; ptcz=2e29b953ce55163edf676cef1baddcd65cbf529e15caf686c5dc44a70bd0a57f; pac_uid=0_DWpnW4Se1GMbM; _qimei_uuid42=18b020b291110018ed0cb79799bdcd1853a9da177b; _qimei_fingerprint=f85b38cc9f1388641316f92802c3da81; _qimei_h38=2db8665aed0cb79799bdcd180200000fe18b02; qq_domain_video_guid_verify=078f1094fb3d98f1; tvfe_boss_uuid=406c5c9d541131c6; pgv_pvid=6916008410; _qimei_q32=aba8d6cb7a8727616eee300ad1d760d3; _qimei_q36=2f8df2a3b15e109877e90a27300019018818; ts_uid=7953382399; fqm_pvqid=e44c8b21-1e15-4b99-9f5e-10ad3d2f04a1; suid=user_0_DWpnW4Se1GMbM; ETCI=3207b28b2b534b2ab473f097b638c0e8; omgid=0_DWpnW4Se1GMbM; ts_refer=678910.cc/; fqm_sessionid=85da44ba-9d2e-406f-a014-3a5a04008827; pgv_info=ssid=s8851706640; ts_last=y.qq.com/"""

# 拆分并转换为字典
cookie_dict = dict(item.strip().split('=', 1) for item in data_str.split('; ') if '=' in item)

# 输出为 JSON 字符串（格式化）
json_output = json.dumps(cookie_dict, indent=4, ensure_ascii=False)

logger.info(json_output)
