from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import At, Plain
from astrbot.api import AstrBotConfig
import os
import json
import logging

@register(
    "astrbot_plugin_at_responder",
    "和泉智宏",
    "针对特定用户的@回复功能，支持全局@、特定群@、全群@和黑名单设置",
    "1.1",
    "https://github.com/0d00-Ciallo-0721/astrbot_plugin_at_responder"
)
class AtReplyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.logger = logging.getLogger("AtReplyPlugin")
        
        # 清理无关配置项（扩展清理列表）
        for old_key in ["target_groups", "target_users", "group_user_pairs", 
                        "at_blacklist", "enabled_groups"]:  # 添加发现的两个无关配置
            if old_key in self.config:
                del self.config[old_key]
                self.logger.info(f"清理无关配置项: {old_key}")
        
        # 1. 初始化全局@列表
        self.global_at_list = self.config.get("global_at_list", [])
        self.global_at_list = [str(id) for id in self.global_at_list]
        
        # 2. 初始化特定群@字典
        try:
            specific_at_json = self.config.get("specific_at_json", "{}")
            self.specific_at_dict = json.loads(specific_at_json)
            
            # 确保所有群ID和用户ID都是字符串
            normalized_dict = {}
            for group_id, user_list in self.specific_at_dict.items():
                normalized_dict[str(group_id)] = [str(user_id) for user_id in user_list]
            self.specific_at_dict = normalized_dict
            
        except json.JSONDecodeError as e:
            self.logger.error(f"解析specific_at_json失败: {e}")
            self.specific_at_dict = {}
        
        # 3. 初始化全群@列表 (新功能)
        self.all_at_groups = self.config.get("all_at_groups", [])
        self.all_at_groups = [str(group_id) for group_id in self.all_at_groups]
        
        # 4. 初始化黑名单 (新功能)
        try:
            blacklist_json = self.config.get("blacklist_json", "{\"全局\":[]}")
            self.blacklist_dict = json.loads(blacklist_json)
            
            # 确保所有群ID和用户ID都是字符串
            normalized_blacklist = {}
            for group_id, user_list in self.blacklist_dict.items():
                normalized_blacklist[str(group_id)] = [str(user_id) for user_id in user_list]
            self.blacklist_dict = normalized_blacklist
            
            # 确保全局黑名单存在
            if "全局" not in self.blacklist_dict:
                self.blacklist_dict["全局"] = []
                
        except json.JSONDecodeError as e:
            self.logger.error(f"解析blacklist_json失败: {e}")
            self.blacklist_dict = {"全局": []}
        
        # 验证配置中只有预期的键
        valid_keys = ["global_at_list", "specific_at_json", "all_at_groups", "blacklist_json"]
        for key in list(self.config.keys()):
            if key not in valid_keys:
                self.logger.warning(f"发现未知配置项: {key}，将被移除")
                del self.config[key]
                
        # 保存配置
        self.config.save_config()
        self.logger.info(f"AT回复插件已加载 - 全局@列表: {self.global_at_list}, 特定群@列表: {self.specific_at_dict}, 全群@列表: {self.all_at_groups}, 黑名单: {self.blacklist_dict}")
        
    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        """拦截所有回复消息，检查是否需要添加@"""
        try:
            # 获取发送者ID和群ID，确保是字符串类型
            sender_id = str(event.get_sender_id())
            group_id = str(event.get_group_id()) if event.get_group_id() else None
            
            # 如果没有结果，直接返回
            result = event.get_result()
            if not result or not result.chain:
                return
            
            # 检查是否添加过@，如已添加则不需处理
            if isinstance(result.chain[0], At):
                return
                
            # 步骤1: 黑名单检查
            is_blacklisted = False
            
            # 检查全局黑名单
            if sender_id in self.blacklist_dict.get("全局", []):
                is_blacklisted = True
                self.logger.debug(f"用户{sender_id}在全局黑名单中，不进行@")
                
            # 检查群特定黑名单
            if not is_blacklisted and group_id and group_id in self.blacklist_dict:
                if sender_id in self.blacklist_dict[group_id]:
                    is_blacklisted = True
                    self.logger.debug(f"用户{sender_id}在群{group_id}的黑名单中，不进行@")
            
            # 如果在黑名单中，不进行@
            if is_blacklisted:
                return
                
            # 步骤2: 三个独立逻辑检查
            need_at = False
            
            # 逻辑1: 检查是否在全群@列表中
            if group_id and group_id in self.all_at_groups:
                need_at = True
                self.logger.debug(f"群{group_id}在全群@列表中，将@用户{sender_id}")
                
            # 逻辑2: 检查是否在全局@列表中
            if not need_at and sender_id in self.global_at_list:
                need_at = True
                self.logger.debug(f"用户{sender_id}在全局@列表中")
                
            # 逻辑3: 检查是否在特定群@列表中
            if not need_at and group_id and group_id in self.specific_at_dict:
                if sender_id in self.specific_at_dict[group_id]:
                    need_at = True
                    self.logger.debug(f"用户{sender_id}在群{group_id}的特定@列表中")
            
            # 如果需要@，添加At到消息链开头
            if need_at:
                self.logger.debug(f"为用户{sender_id}添加@")
                # 添加At到消息链开头
                result.chain.insert(0, At(qq=sender_id))
                # 如果第一个元素是Plain，且以空格开头，去掉空格
                if len(result.chain) > 1 and isinstance(result.chain[1], Plain):
                    if result.chain[1].text.startswith(" "):
                        result.chain[1].text = result.chain[1].text.lstrip()
        except Exception as e:
            self.logger.error(f"处理@响应时出错: {e}")

    @filter.command("at_status")
    async def at_status(self, event: AstrMessageEvent):
        """查看当前用户的@状态"""
        sender_id = str(event.get_sender_id())
        group_id = str(event.get_group_id()) if event.get_group_id() else None
        
        status_lines = ["你的@状态："]
        
        # 检查黑名单状态
        in_global_blacklist = sender_id in self.blacklist_dict.get("全局", [])
        in_group_blacklist = group_id and group_id in self.blacklist_dict and sender_id in self.blacklist_dict[group_id]
        
        if in_global_blacklist:
            status_lines.append("⚠️ 你在全局黑名单中，不会被@")
        elif in_group_blacklist:
            status_lines.append("⚠️ 你在当前群的黑名单中，不会被@")
        else:
            # 检查全局@状态
            in_global_at = sender_id in self.global_at_list
            status_lines.append(f"全局@: {'✅ 在全局@名单中' if in_global_at else '❌ 不在全局@名单中'}")
            
            # 检查群全体@状态
            if group_id:
                in_all_at_group = group_id in self.all_at_groups
                status_lines.append(f"群全体@: {'✅ 当前群启用全体@' if in_all_at_group else '❌ 当前群未启用全体@'}")
            
            # 检查特定群@状态
            if group_id:
                in_specific_at = group_id in self.specific_at_dict and sender_id in self.specific_at_dict[group_id]
                status_lines.append(f"特定群@: {'✅ 在当前群的特定@名单中' if in_specific_at else '❌ 不在当前群的特定@名单中'}")
        
        yield event.plain_result("\n".join(status_lines))

    # 全局@管理命令
    @filter.command("at_add_global")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def at_add_global(self, event: AstrMessageEvent, qq_id: str):
        """添加用户到全局@列表"""
        qq_id = str(qq_id)
        if qq_id not in self.global_at_list:
            self.global_at_list.append(qq_id)
            self.config["global_at_list"] = self.global_at_list
            self.config.save_config()
            yield event.plain_result(f"已将用户 {qq_id} 添加到全局@列表")
        else:
            yield event.plain_result(f"用户 {qq_id} 已在全局@列表中")

    @filter.command("at_remove_global")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def at_remove_global(self, event: AstrMessageEvent, qq_id: str):
        """从全局@列表移除用户"""
        qq_id = str(qq_id)
        if qq_id in self.global_at_list:
            self.global_at_list.remove(qq_id)
            self.config["global_at_list"] = self.global_at_list
            self.config.save_config()
            yield event.plain_result(f"已将用户 {qq_id} 从全局@列表移除")
        else:
            yield event.plain_result(f"用户 {qq_id} 不在全局@列表中")

    # 特定群@管理命令
    @filter.command("at_add_specific")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def at_add_specific(self, event: AstrMessageEvent, qq_id: str):
        """添加用户到特定群@列表"""
        qq_id = str(qq_id)
        group_id = str(event.get_group_id()) if event.get_group_id() else None
        if not group_id:
            yield event.plain_result("此命令只能在群聊中使用")
            return
            
        if group_id not in self.specific_at_dict:
            self.specific_at_dict[group_id] = []
            
        if qq_id not in self.specific_at_dict[group_id]:
            self.specific_at_dict[group_id].append(qq_id)
            # 保存到配置
            self.config["specific_at_json"] = json.dumps(self.specific_at_dict)
            self.config.save_config()
            yield event.plain_result(f"已将用户 {qq_id} 添加到当前群的特定@列表")
        else:
            yield event.plain_result(f"用户 {qq_id} 已在当前群的特定@列表中")

    @filter.command("at_remove_specific")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def at_remove_specific(self, event: AstrMessageEvent, qq_id: str):
        """从特定群@列表移除用户"""
        qq_id = str(qq_id)
        group_id = str(event.get_group_id()) if event.get_group_id() else None
        if not group_id:
            yield event.plain_result("此命令只能在群聊中使用")
            return
            
        if group_id in self.specific_at_dict and qq_id in self.specific_at_dict[group_id]:
            self.specific_at_dict[group_id].remove(qq_id)
            # 保存到配置
            self.config["specific_at_json"] = json.dumps(self.specific_at_dict)
            self.config.save_config()
            yield event.plain_result(f"已将用户 {qq_id} 从当前群的特定@列表移除")
        else:
            yield event.plain_result(f"用户 {qq_id} 不在当前群的特定@列表中")

    # 全群@管理命令 (新增)
    @filter.command("at_add_group")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def at_add_group(self, event: AstrMessageEvent, group_id: str = None):
        """添加群到全群@列表"""
        if not group_id:
            group_id = str(event.get_group_id()) if event.get_group_id() else None
            if not group_id:
                yield event.plain_result("请在群聊中使用此命令或指定群号")
                return
                
        group_id = str(group_id)
        if group_id not in self.all_at_groups:
            self.all_at_groups.append(group_id)
            self.config["all_at_groups"] = self.all_at_groups
            self.config.save_config()
            yield event.plain_result(f"已将群 {group_id} 添加到全群@列表")
        else:
            yield event.plain_result(f"群 {group_id} 已在全群@列表中")

    @filter.command("at_remove_group")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def at_remove_group(self, event: AstrMessageEvent, group_id: str = None):
        """从全群@列表移除群"""
        if not group_id:
            group_id = str(event.get_group_id()) if event.get_group_id() else None
            if not group_id:
                yield event.plain_result("请在群聊中使用此命令或指定群号")
                return
                
        group_id = str(group_id)
        if group_id in self.all_at_groups:
            self.all_at_groups.remove(group_id)
            self.config["all_at_groups"] = self.all_at_groups
            self.config.save_config()
            yield event.plain_result(f"已将群 {group_id} 从全群@列表移除")
        else:
            yield event.plain_result(f"群 {group_id} 不在全群@列表中")

    # 黑名单管理命令 (新增)
    @filter.command("at_add_blacklist")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def at_add_blacklist(self, event: AstrMessageEvent, qq_id: str, is_global: bool = False):
        """添加用户到黑名单"""
        qq_id = str(qq_id)
        
        if is_global:
            # 添加到全局黑名单
            if qq_id not in self.blacklist_dict["全局"]:
                self.blacklist_dict["全局"].append(qq_id)
                self.config["blacklist_json"] = json.dumps(self.blacklist_dict)
                self.config.save_config()
                yield event.plain_result(f"已将用户 {qq_id} 添加到全局黑名单")
            else:
                yield event.plain_result(f"用户 {qq_id} 已在全局黑名单中")
        else:
            # 添加到群黑名单
            group_id = str(event.get_group_id()) if event.get_group_id() else None
            if not group_id:
                yield event.plain_result("在非群聊中添加到群黑名单时需指定is_global=True")
                return
                
            if group_id not in self.blacklist_dict:
                self.blacklist_dict[group_id] = []
                
            if qq_id not in self.blacklist_dict[group_id]:
                self.blacklist_dict[group_id].append(qq_id)
                self.config["blacklist_json"] = json.dumps(self.blacklist_dict)
                self.config.save_config()
                yield event.plain_result(f"已将用户 {qq_id} 添加到当前群的黑名单")
            else:
                yield event.plain_result(f"用户 {qq_id} 已在当前群的黑名单中")

    @filter.command("at_remove_blacklist")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def at_remove_blacklist(self, event: AstrMessageEvent, qq_id: str, is_global: bool = False):
        """从黑名单移除用户"""
        qq_id = str(qq_id)
        
        if is_global:
            # 从全局黑名单移除
            if qq_id in self.blacklist_dict["全局"]:
                self.blacklist_dict["全局"].remove(qq_id)
                self.config["blacklist_json"] = json.dumps(self.blacklist_dict)
                self.config.save_config()
                yield event.plain_result(f"已将用户 {qq_id} 从全局黑名单移除")
            else:
                yield event.plain_result(f"用户 {qq_id} 不在全局黑名单中")
        else:
            # 从群黑名单移除
            group_id = str(event.get_group_id()) if event.get_group_id() else None
            if not group_id:
                yield event.plain_result("在非群聊中从群黑名单移除时需指定is_global=True")
                return
                
            if group_id in self.blacklist_dict and qq_id in self.blacklist_dict[group_id]:
                self.blacklist_dict[group_id].remove(qq_id)
                self.config["blacklist_json"] = json.dumps(self.blacklist_dict)
                self.config.save_config()
                yield event.plain_result(f"已将用户 {qq_id} 从当前群的黑名单移除")
            else:
                yield event.plain_result(f"用户 {qq_id} 不在当前群的黑名单中")

    @filter.command("at_list")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def at_list(self, event: AstrMessageEvent):
        """显示所有@配置"""
        status = []
        
        # 全局@列表
        status.append("📋 全局@列表:")
        if self.global_at_list:
            status.append("  " + ", ".join(self.global_at_list))
        else:
            status.append("  无")
            
        # 全群@列表
        status.append("\n📋 全群@列表:")
        if self.all_at_groups:
            status.append("  " + ", ".join(self.all_at_groups))
        else:
            status.append("  无")
            
        # 特定群@配置
        status.append("\n📋 特定群@配置:")
        if self.specific_at_dict:
            for group_id, users in self.specific_at_dict.items():
                status.append(f"  群 {group_id}: {', '.join(users)}")
        else:
            status.append("  无")
            
        # 黑名单配置
        status.append("\n📋 黑名单配置:")
        has_blacklist = False
        
        if "全局" in self.blacklist_dict and self.blacklist_dict["全局"]:
            has_blacklist = True
            status.append(f"  全局: {', '.join(self.blacklist_dict['全局'])}")
            
        for group_id, users in self.blacklist_dict.items():
            if group_id != "全局" and users:
                has_blacklist = True
                status.append(f"  群 {group_id}: {', '.join(users)}")
                
        if not has_blacklist:
            status.append("  无")
            
        yield event.plain_result("\n".join(status))

    async def terminate(self):
        """插件终止时保存配置"""
        self.config.save_config()
