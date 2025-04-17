# AstrBot @回复插件

一个用于自动为特定用户或特定群聊添加@回复的AstrBot插件。支持全局@、特定群@、全群@以及黑名单功能。

## 功能特点

- **全局@功能**: 对指定用户在任何群聊中都自动添加@
- **特定群@功能**: 仅在特定群聊中对特定用户自动添加@
- **全群@功能**: 在指定群聊中对所有用户自动添加@
- **黑名单功能**: 对黑名单内用户不进行@回复
- **配置灵活**: 支持WebUI界面配置
- **多重判断逻辑**: 独立的判断机制确保@回复行为符合预期


## 配置说明

插件提供四种配置项：

1. **全局@列表**: 添加在这个列表中的QQ号将在所有群聊中被@
2. **特定群@配置**: JSON格式，配置特定群中需要@的特定用户
3. **全群@列表**: 添加在这个列表中的群号，其中所有用户都会被@
4. **黑名单配置**: JSON格式，配置全局黑名单和群特定黑名单

## 示例配置
**全局@列表**:
123456789
987654321


**特定群@配置**:
```json
{"123456":["11111111","22222222"], "654321":["33333333"]}
全群@列表:
123456789
987654321
黑名单配置:

{"全局":["12345678"], "123456":["11111111"]}




## 指令列表

| 指令 | 参数 | 权限 | 说明 |
|------|------|------|------|
| `/at_status` | 无 | 所有人 | 查看当前用户的@状态 |
| `/at_list` | 无 | 管理员 | 显示所有@配置 |
| `/at_add_global` | QQ号 | 管理员 | 添加用户到全局@列表 |
| `/at_remove_global` | QQ号 | 管理员 | 从全局@列表移除用户 |
| `/at_add_specific` | QQ号 | 管理员 | 添加用户到当前群的特定@列表 |
| `/at_remove_specific` | QQ号 | 管理员 | 从当前群的特定@列表移除用户 |
| `/at_add_group` | 群号| 管理员 | 添加群到全群@列表(不填则为当前群) |
| `/at_remove_group` | 群号 | 管理员 | 从全群@列表移除群(不填则为当前群) |

## 工作流程

1. 接收消息后先判断发送者是否在黑名单中
2. 如不在黑名单，按以下三个独立逻辑判断是否需要@:
   - 检查当前群是否在全群@列表中
   - 检查用户是否在全局@列表中
   - 检查用户是否在特定群@列表中
3. 只要符合任一条件即添加@回复，三条都不符合则不添加@

## 注意事项

- 黑名单优先级最高，会覆盖其他@设置
- 三个判断逻辑是独立的，不互相影响
- 所有配置更改会实时保存
- 如配置WebUI中的JSON格式有误，插件会使用默认空值

