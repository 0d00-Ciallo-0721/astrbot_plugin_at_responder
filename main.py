from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import At, Plain
from astrbot.api import AstrBotConfig, logger
import os
import json
import asyncio
import functools
from typing import Set, Dict, Optional, Union, List, Any
from collections import defaultdict
from functools import lru_cache

@register(
    "astrbot_plugin_at_responder",
    "和泉智宏",
    "针对特定用户的@回复功能，支持全局@、特定群@、全群@和黑名单设置",
    "1.3",
    "https://github.com/0d00-Ciallo-0721/astrbot_plugin_at_responder"
)
class AtReplyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._config_changed = False
        
        # 延迟加载标志
        self._configs_loaded = False
        self._global_at_set = None
        self._all_at_groups_set = None
        self._specific_at_dict = None
        self._blacklist_dict = None
        self._keyword_blacklist_set = None
        
        # 初始加载配置
        self._ensure_configs_loaded()
        
    def _ensure_configs_loaded(self):
        """确保配置已加载（懒加载）"""
        if not self._configs_loaded:
            self._load_configs()
            self._configs_loaded = True
    
    def _load_configs(self):
        """加载所有配置，使用原子性操作防止竞态条件"""
        # 清理无关配置项
        for old_key in ["target_groups", "target_users", "group_user_pairs", 
                       "at_blacklist", "enabled_groups"]:
            if old_key in self.config:
                del self.config[old_key]
                self._config_changed = True
        
        try:
            # 先加载到临时变量，确保原子性
            temp_global_at_set = set(str(x) for x in self.config.get("global_at_list", []))
            temp_all_at_groups_set = set(str(x) for x in self.config.get("all_at_groups", []))
            temp_keyword_blacklist_set = set(str(x).lower() for x in self.config.get("keyword_blacklist", []))
            
            # 处理特定群@字典
            temp_specific_at_dict = defaultdict(set)
            spec_data = self.config.get("specific_at_json", "{}")
            if spec_data and spec_data.strip():
                try:
                    if isinstance(spec_data, str):
                        spec_data = json.loads(spec_data)
                    for group_id, users in spec_data.items():
                        temp_specific_at_dict[str(group_id)] = set(str(u) for u in users)
                except json.JSONDecodeError:
                    logger.warning("specific_at_json 格式无效，将使用空配置")
                    # 解析失败时使用空字典，但不影响其他配置的加载
                    temp_specific_at_dict = defaultdict(set)
            
            # 处理黑名单字典
            temp_blacklist_dict = defaultdict(set)
            blacklist_data = self.config.get("blacklist_json", '{"全局":[]}')
            if blacklist_data and blacklist_data.strip():
                try:
                    if isinstance(blacklist_data, str):
                        blacklist_data = json.loads(blacklist_data)
                    for group_id, users in blacklist_data.items():
                        temp_blacklist_dict[str(group_id)] = set(str(u) for u in users)
                except json.JSONDecodeError:
                    logger.warning("blacklist_json 格式无效，将使用默认配置")
                    # 解析失败时使用默认值，但不影响其他配置的加载
                    temp_blacklist_dict = defaultdict(set)
                    temp_blacklist_dict["全局"] = set()
            
            # 所有解析都完成后，原子性地更新实例变量
            self._global_at_set = temp_global_at_set
            self._all_at_groups_set = temp_all_at_groups_set
            self._keyword_blacklist_set = temp_keyword_blacklist_set
            self._specific_at_dict = temp_specific_at_dict
            self._blacklist_dict = temp_blacklist_dict
            
            # 验证配置中只有预期的键
            valid_keys = {"global_at_list", "specific_at_json", "all_at_groups", "blacklist_json", "keyword_blacklist"}
            for key in list(self.config.keys()):
                if key not in valid_keys:
                    del self.config[key]
                    self._config_changed = True
            
            # 如果配置有变更，保存
            if self._config_changed:
                self._save_config()
                self._config_changed = False
                
            logger.debug(f"配置加载完成 - 全局@: {len(self._global_at_set)}人, "
                        f"全群@: {len(self._all_at_groups_set)}群, "
                        f"关键词黑名单: {len(self._keyword_blacklist_set)}个")
            
            # 清理所有缓存
            if hasattr(self._is_blacklisted, 'cache_clear'):
                self._is_blacklisted.cache_clear()
                logger.debug("已清理黑名单检查缓存")
            
            if hasattr(self._need_at, 'cache_clear'):
                self._need_at.cache_clear()
                logger.debug("已清理@需求检查缓存")
                
            self._configs_loaded = True
        except Exception as e:
            logger.error(f"加载配置时发生错误: {e}")
            # 如果是首次加载且失败，初始化为空集合
            if self._global_at_set is None:
                self._global_at_set = set()
                self._all_at_groups_set = set()
                self._keyword_blacklist_set = set()
                self._specific_at_dict = defaultdict(set)
                self._blacklist_dict = defaultdict(set)
                self._blacklist_dict["全局"] = set()
    
    def _save_config(self):
        """仅在配置有变更时保存"""
        try:
            # 将**转为列表保存
            self.config["global_at_list"] = list(self._global_at_set)
            self.config["all_at_groups"] = list(self._all_at_groups_set)
            self.config["keyword_blacklist"] = list(self._keyword_blacklist_set)
            
            # 处理字典数据
            specific_dict = {k: list(v) for k, v in self._specific_at_dict.items() if v}
            blacklist_dict = {k: list(v) for k, v in self._blacklist_dict.items() if v}
            
            self.config["specific_at_json"] = json.dumps(specific_dict)
            self.config["blacklist_json"] = json.dumps(blacklist_dict)
            
            self.config.save_config()
            self._config_changed = False
            logger.info("配置已保存")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
    
    # 使用LRU缓存提高频繁检查的性能
    @lru_cache(maxsize=256, typed=True)
    def _is_blacklisted(self, sender_id: str, group_id: Optional[str]) -> bool:
        """检查用户是否在黑名单中（使用缓存）"""
        self._ensure_configs_loaded()
        # 使用更简洁的条件判断
        return (sender_id in self._blacklist_dict["全局"] or 
                (group_id and sender_id in self._blacklist_dict[group_id]))
    
    def _has_blacklisted_keyword(self, message_text: str) -> bool:
        """检查消息是否包含黑名单关键词"""
        self._ensure_configs_loaded()
        if not self._keyword_blacklist_set or not message_text:
            return False
            
        message_text = message_text.lower()
        for keyword in self._keyword_blacklist_set:
            if keyword in message_text:
                logger.debug(f"消息中包含黑名单关键词: {keyword}")
                return True
        return False
    
    @lru_cache(maxsize=256, typed=True)
    def _need_at(self, sender_id: str, group_id: Optional[str]) -> bool:
        """检查是否需要@该用户（使用缓存）"""
        self._ensure_configs_loaded()
        # 使用短路逻辑简化判断
        return (sender_id in self._global_at_set or
                (group_id and group_id in self._all_at_groups_set) or
                (group_id and sender_id in self._specific_at_dict[group_id]))

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        """拦截回复消息，检查是否需要@"""
        try:
            # 快速返回条件
            result = event.get_result()
            if not result or not result.chain or isinstance(result.chain[0], At):
                return
                
            sender_id = str(event.get_sender_id())
            group_id = str(event.get_group_id()) if event.get_group_id() else None
            
            # 用户黑名单检查
            if self._is_blacklisted(sender_id, group_id):
                logger.debug(f"用户 {sender_id} 在黑名单中，不进行@")
                return
            
            # 关键词黑名单检查
            message_text = event.message_str  # 使用message_str属性获取纯文本
            if message_text and self._has_blacklisted_keyword(message_text):
                logger.debug(f"用户 {sender_id} 消息包含黑名单关键词，不进行@")
                return
                
            if self._need_at(sender_id, group_id):
                logger.debug(f"用户 {sender_id} 需要被@")
                # 添加At
                result.chain.insert(0, At(qq=sender_id))
                # 优化空格：使用条件表达式
                if len(result.chain) > 1 and isinstance(result.chain[1], Plain):
                    result.chain[1].text = result.chain[1].text.lstrip()
            else:
                logger.debug(f"用户 {sender_id} 不需要被@")
        except Exception as e:
            logger.error(f"@处理错误: {e}")

    @filter.command("at_status")
    async def at_status(self, event: AstrMessageEvent):
        """查看当前用户的@状态"""
        sender_id = str(event.get_sender_id())
        group_id = str(event.get_group_id()) if event.get_group_id() else None
        
        # 使用列表推导生成状态信息
        self._ensure_configs_loaded()
        
        if self._is_blacklisted(sender_id, group_id):
            status = ["你的@状态：", "⚠️ 你在黑名单中，不会被@"]
        elif self._need_at(sender_id, group_id):
            status = ["你的@状态：", "✅ 你会被@回复"]
            
            # 使用列表推导简化原因说明
            reasons = []
            if sender_id in self._global_at_set:
                reasons.append("  - 你在全局@名单中")
            if group_id and group_id in self._all_at_groups_set:
                reasons.append("  - 当前群启用全体@")
            if group_id and sender_id in self._specific_at_dict[group_id]:
                reasons.append("  - 你在当前群的特定@名单中")
            
            status.extend(reasons)
            
            # 添加关键词黑名单提示
            if self._keyword_blacklist_set:
                status.append("  - 但如果消息中含有特定关键词，仍不会被@")
        else:
            status = ["你的@状态：", "❌ 你不会被@回复"]
        
        yield event.plain_result("\n".join(status))

    @filter.command("at_reload_config")
    async def at_reload_config(self, event: AstrMessageEvent):
        """重新加载配置"""
        if not event.is_admin():
            yield event.plain_result("⚠️ 权限不足，仅管理员可重载配置")
            return
            
        self._configs_loaded = False
        self._ensure_configs_loaded()
        yield event.plain_result("✅ 配置已重新加载")
        
    @filter.command("at_cache_info")
    async def at_cache_info(self, event: AstrMessageEvent):
        """查看缓存状态信息"""
        if not event.is_admin():
            yield event.plain_result("⚠️ 权限不足，仅管理员可查看缓存信息")
            return
            
        info = [
            "缓存状态信息：",
            f"黑名单检查缓存: {self._is_blacklisted.cache_info()}",
            f"@需求检查缓存: {self._need_at.cache_info()}",
            f"关键词黑名单数量: {len(self._keyword_blacklist_set)}个"
        ]
        
        yield event.plain_result("\n".join(info))

    async def terminate(self):
        """插件终止时保存配置"""
        if self._config_changed and self._configs_loaded:
            try:
                self._save_config()
                logger.info("插件终止，配置已保存")
            except Exception as e:
                logger.error(f"终止保存失败: {e}")
