# 一刻相册一键下载
一刻相册一键全部下载

多线程下载+断点重续+检测重复文件+重新下载失败文件+记录日志+自动创建目录+下载总结
## 依赖
基于Python3的脚本，因此首先你得有Python3
### 安装第三方库
#### 发送 HTTP 请求
```
pip install requests
```
#### 显示进度条
```
pip install tqdm
```
## 准备
打开一刻相册网页端，按下F12，在DevTools内点击上方的`网络`，然后点击`Fetch/XHR`进行筛选。

![image](https://github.com/user-attachments/assets/ddbc2d08-ee89-4d47-b1a8-2363a7929e32)


点击列表的list?celienttype=70……，在请求标头找到`cookie`.三击全选复制。

![image](https://github.com/user-attachments/assets/f1f5b3d4-04dc-48a1-af52-e23f741d43bb)


点击上方负载，双击`bdstoken`的字段。

![image](https://github.com/user-attachments/assets/5fcfd587-91e4-4dfe-8380-efc12a55e6ce)

在`settings.json`里面，填写对应的`bdstoken`和`Cookie`，如果`Cookie`值中有双引号，则用转义字符`\"`代替双引号`"`

![image](https://github.com/user-attachments/assets/d5590d6b-d8b3-4803-85d4-4c937aff8f16)

## 运行
cmd进入py文件所在目录，先找照片的元数据
```
python photographListDownload.py
```
然后运行下载
```
python photographDownload.py
```
等待完成即可
## 注意
你所有复制的数据包含你的隐私数据，请勿告诉他人。
