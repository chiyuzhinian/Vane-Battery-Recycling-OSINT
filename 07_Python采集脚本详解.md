# 🐍 Python采集脚本详解

## 第一部分：脚本架构和依赖

### 1.1 项目结构

```
scripts/
├── __init__.py
├── requirements.txt
├── config.yaml
├── collect_company.py           # 主采集脚本
├── collect_policies.py          # 政策监测脚本
├── modules/
│   ├── __init__.py
│   ├── vane_search.py          # Vane搜索调用
│   ├── query_decomposer.py     # 需求拆解模块
│   ├── data_validator.py       # 数据验证模块
│   ├── claude_analyzer.py      # Claude分析模块
│   ├── database.py             # 数据库操作
│   └── utils.py                # 工具函数
└── tests/
    └── test_collect.py
```

### 1.2 依赖安装

```bash
# requirements.txt

# 核心依赖
requests>=2.31.0
httpx>=0.24.0
anthropic>=0.7.0          # Claude API
pyyaml>=6.0               # 配置文件
python-dotenv>=1.0.0      # 环境变量
pymysql>=1.1.0            # MySQL数据库
sqlalchemy>=2.0.0         # ORM
aliyun-python-sdk-oss>=2.18.0  # 阿里云OSS

# 数据处理
pandas>=2.0.0
numpy>=1.24.0

# 日志和监控
python-json-logger>=2.0.0
loguru>=0.7.0

# 并发和异步
asyncio>=3.11.0
aiohttp>=3.8.0

# 数据验证
pydantic>=2.0.0

# 定时任务
schedule>=1.2.0
APScheduler>=3.10.0

# 测试
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

### 1.3 环境配置

```bash
# .env.local

# Vane配置
VANE_URL=http://localhost:3000
VANE_API_KEY=your_key_here

# Claude配置
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-3-5-sonnet-20241022

# 数据库配置
MYSQL_HOST=your-db-host.rds.aliyuncs.com
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=battery_osint

# 云存储配置
ALIYUN_OSS_ACCESS_KEY_ID=xxxxx
ALIYUN_OSS_ACCESS_KEY_SECRET=xxxxx
ALIYUN_OSS_BUCKET=battery-osint
ALIYUN_OSS_REGION=oss-cn-beijing

# 日志级别
LOG_LEVEL=INFO
```

---

## 第二部分：核心采集脚本

### 2.1 主采集脚本

```python
# scripts/collect_company.py

import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any
from loguru import logger
from modules.query_decomposer import QueryDecomposer
from modules.vane_search import VaneSearcher
from modules.data_validator import DataValidator
from modules.claude_analyzer import ClaudeAnalyzer
from modules.database import Database
from modules.utils import load_config

class CompanyCollector:
    """
    电池回收企业OSINT采集器
    
    工作流程：
    1. 需求拆解 → 将用户需求转换为多个搜索查询
    2. 多源搜证 → 并行调用Vane搜索API
    3. 数据验证 → 多层次验证和去重
    4. 深度分析 → 调用Claude进行分析
    5. 数据存储 → 保存到云端数据库
    """
    
    def __init__(self, config_path: str = 'config.yaml'):
        self.config = load_config(config_path)
        self.decomposer = QueryDecomposer()
        self.searcher = VaneSearcher(self.config)
        self.validator = DataValidator(self.config)
        self.analyzer = ClaudeAnalyzer(self.config)
        self.db = Database(self.config)
        
        logger.add("logs/collect_{time}.log", rotation="500 MB")
    
    async def collect(
        self,
        companies: List[str],
        dimensions: List[str] = None,
        quality_threshold: int = 70,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        主采集方法
        
        Args:
            companies: 企业名称列表
            dimensions: 采集维度列表
            quality_threshold: 质量阈值（0-100）
            verbose: 是否输出详细日志
        
        Returns:
            采集结果字典
        """
        
        logger.info(f"开始采集企业信息: {companies}")
        logger.info(f"采集维度: {dimensions or '全部'}")
        logger.info(f"质量阈值: {quality_threshold}")
        
        start_time = datetime.now()
        results = {
            'companies': companies,
            'dimensions': dimensions or self._get_all_dimensions(),
            'timestamp': start_time.isoformat(),
            'data': {},
            'statistics': {}
        }
        
        try:
            # 步骤1：需求拆解
            logger.info("步骤1: 需求拆解")
            queries = await self._decompose_requirements(
                companies=companies,
                dimensions=results['dimensions']
            )
            logger.info(f"生成搜索查询 {len(queries)} 条")
            
            # 步骤2：多源搜证
            logger.info("步骤2: 多源搜证")
            raw_results = await self._search_all_sources(queries)
            logger.info(f"获取原始搜索结果 {len(raw_results)} 条")
            
            # 步骤3：数据验证和去重
            logger.info("步骤3: 数据验证和去重")
            validated_data = await self._validate_data(raw_results)
            logger.info(f"验证通过 {len(validated_data)} 条数据")
            
            # 步骤4：数据过滤（按质量阈值）
            high_quality_data = [
                d for d in validated_data 
                if d.get('quality_score', 0) >= quality_threshold
            ]
            low_quality_data = [
                d for d in validated_data 
                if d.get('quality_score', 0) < quality_threshold
            ]
            logger.info(
                f"高质量数据: {len(high_quality_data)}, "
                f"待审核数据: {len(low_quality_data)}"
            )
            
            # 步骤5：深度分析（可选）
            if self.config.get('enable_claude_analysis', True):
                logger.info("步骤5: Claude深度分析")
                analysis = await self._perform_analysis(
                    companies=companies,
                    data=high_quality_data
                )
                results['analysis'] = analysis
            
            # 步骤6：数据存储
            logger.info("步骤6: 数据存储")
            await self._save_to_database(
                high_quality_data,
                low_quality_data
            )
            
            # 统计信息
            duration = (datetime.now() - start_time).total_seconds()
            results['statistics'] = {
                'total_results': len(raw_results),
                'validated_data': len(validated_data),
                'high_quality': len(high_quality_data),
                'low_quality': len(low_quality_data),
                'duration_seconds': duration,
                'avg_quality_score': sum(
                    d.get('quality_score', 0) for d in validated_data
                ) / len(validated_data) if validated_data else 0
            }
            
            logger.info(
                f"采集完成! 耗时 {duration:.1f}秒, "
                f"高质量数据 {len(high_quality_data)}条"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"采集过程出错: {str(e)}", exc_info=True)
            raise
    
    async def _decompose_requirements(
        self,
        companies: List[str],
        dimensions: List[str]
    ) -> List[Dict[str, Any]]:
        """
        需求拆解：将采集需求转换为搜索查询
        """
        queries = []
        
        for company in companies:
            for dimension in dimensions:
                # 根据维度生成查询模板
                dimension_queries = self.decomposer.generate_queries(
                    company=company,
                    dimension=dimension
                )
                queries.extend(dimension_queries)
        
        # 按优先级排序
        queries.sort(key=lambda q: q.get('priority', 999))
        
        return queries
    
    async def _search_all_sources(
        self,
        queries: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        多源搜证：并行调用Vane搜索API
        """
        # 创建搜索任务
        tasks = [
            self.searcher.search(query)
            for query in queries
        ]
        
        # 并行执行
        results = []
        for i, task in enumerate(asyncio.as_completed(tasks), 1):
            try:
                result = await task
                results.extend(result)
                if i % 5 == 0:
                    logger.debug(f"已完成 {i}/{len(queries)} 个搜索查询")
            except Exception as e:
                logger.warning(f"搜索查询失败: {str(e)}")
        
        return results
    
    async def _validate_data(
        self,
        raw_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        数据验证：多层次验证和去重
        """
        # 步骤1：去噪
        cleaned = self.validator.filter_noise(raw_results)
        
        # 步骤2：去重
        deduplicated = self.validator.deduplicate(cleaned)
        
        # 步骤3：信息提取
        structured = await self.validator.extract_structure(deduplicated)
        
        # 步骤4：多源交叉验证
        cross_validated = self.validator.cross_validate(structured)
        
        # 步骤5：AI逻辑检查
        ai_checked = await self.validator.ai_logic_check(cross_validated)
        
        # 步骤6：质量评分
        scored = self.validator.calculate_quality_scores(ai_checked)
        
        return scored
    
    async def _perform_analysis(
        self,
        companies: List[str],
        data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        调用Claude进行深度分析
        """
        analysis = await self.analyzer.analyze(
            companies=companies,
            data=data
        )
        return analysis
    
    async def _save_to_database(
        self,
        high_quality_data: List[Dict[str, Any]],
        low_quality_data: List[Dict[str, Any]]
    ):
        """
        保存数据到数据库
        """
        # 保存高质量数据
        for item in high_quality_data:
            await self.db.insert_company_data(item)
        
        # 保存待审核数据
        for item in low_quality_data:
            await self.db.insert_pending_review(item)
        
        logger.info(
            f"已保存数据: "
            f"{len(high_quality_data)}条入库, "
            f"{len(low_quality_data)}条待审"
        )
    
    def _get_all_dimensions(self) -> List[str]:
        """获取所有采集维度"""
        return ['人力资源', '经营现状', '战略规划', '工艺技术', '废料来源']


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='电池回收企业OSINT采集')
    parser.add_argument(
        '--companies',
        nargs='+',
        required=True,
        help='企业名称列表，用空格分隔'
    )
    parser.add_argument(
        '--dimensions',
        nargs='+',
        default=None,
        help='采集维度列表，用空格分隔'
    )
    parser.add_argument(
        '--quality-threshold',
        type=int,
        default=70,
        help='质量阈值 (0-100)'
    )
    parser.add_argument(
        '--output',
        default='data/results.json',
        help='输出文件路径'
    )
    
    args = parser.parse_args()
    
    # 初始化采集器
    collector = CompanyCollector()
    
    # 执行采集
    results = await collector.collect(
        companies=args.companies,
        dimensions=args.dimensions,
        quality_threshold=args.quality_threshold
    )
    
    # 保存结果
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    logger.info(f"采集结果已保存到 {args.output}")
    
    # 打印统计
    stats = results['statistics']
    print("\n采集统计:")
    print(f"  原始搜索结果: {stats['total_results']}")
    print(f"  已验证数据: {stats['validated_data']}")
    print(f"  高质量数据: {stats['high_quality']}")
    print(f"  待审核数据: {stats['low_quality']}")
    print(f"  平均质量分: {stats['avg_quality_score']:.1f}/100")
    print(f"  总耗时: {stats['duration_seconds']:.1f}秒")


if __name__ == '__main__':
    asyncio.run(main())
```

---

## 第三部分：模块详解

### 3.1 Vane搜索模块

```python
# scripts/modules/vane_search.py

import httpx
import asyncio
from typing import List, Dict, Any
from loguru import logger

class VaneSearcher:
    """调用Vane搜索API"""
    
    def __init__(self, config: Dict[str, Any]):
        self.vane_url = config.get('vane_url', 'http://localhost:3000')
        self.vane_api_key = config.get('vane_api_key', '')
        self.timeout = config.get('search_timeout', 30)
    
    async def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        调用Vane搜索API
        
        Args:
            query: {
                'text': '搜索文本',
                'mode': 'quality/balanced/speed',
                'dimension': '维度',
                'priority': 优先级,
                'expected_results': 期望结果数
            }
        
        Returns:
            搜索结果列表
        """
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f'{self.vane_url}/api/search',
                    json={
                        'query': query['text'],
                        'mode': query.get('mode', 'balanced'),
                        'stream': False
                    },
                    timeout=self.timeout
                )
                
                if response.status_code != 200:
                    logger.warning(
                        f"Vane搜索失败: {query['text']}, "
                        f"状态码: {response.status_code}"
                    )
                    return []
                
                data = response.json()
                
                # 处理搜索结果
                results = []
                for source in data.get('sources', []):
                    results.append({
                        'query_id': query.get('id'),
                        'query_text': query['text'],
                        'dimension': query.get('dimension'),
                        'source_name': source.get('url', '').split('/')[2],  # 域名
                        'title': source.get('title'),
                        'url': source.get('url'),
                        'snippet': source.get('content', ''),
                        'timestamp': datetime.now().isoformat()
                    })
                
                logger.debug(
                    f"搜索'{query['text']}'获得 {len(results)} 条结果"
                )
                
                return results
                
            except asyncio.TimeoutError:
                logger.warning(f"搜索超时: {query['text']}")
                return []
            except Exception as e:
                logger.error(f"搜索异常: {str(e)}", exc_info=True)
                return []
```

### 3.2 数据验证模块

```python
# scripts/modules/data_validator.py

import hashlib
from typing import List, Dict, Any
from anthropic import Anthropic

class DataValidator:
    """数据验证和质量评分"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.claude_client = Anthropic()
    
    def filter_noise(self, results: List[Dict]) -> List[Dict]:
        """去噪：过滤垃圾信息"""
        cleaned = []
        
        for result in results:
            # 检查snippet长度
            if len(result.get('snippet', '')) < 20:
                continue
            
            # 检查是否是广告或错误页面
            if self._is_advertisement(result['snippet']):
                continue
            
            if self._is_error_page(result['url']):
                continue
            
            cleaned.append(result)
        
        return cleaned
    
    def deduplicate(self, results: List[Dict]) -> List[Dict]:
        """去重：合并相同内容"""
        seen = {}
        
        for result in results:
            # 计算内容哈希
            content_hash = hashlib.md5(
                result['snippet'].encode()
            ).hexdigest()
            
            if content_hash not in seen:
                seen[content_hash] = result
                result['sources'] = [{'url': result['url'], 'source': result['source_name']}]
            else:
                # 合并来源
                seen[content_hash]['sources'].append({
                    'url': result['url'],
                    'source': result['source_name']
                })
        
        return list(seen.values())
    
    async def extract_structure(self, results: List[Dict]) -> List[Dict]:
        """信息提取：转换为结构化数据"""
        structured = []
        
        for result in results:
            # 使用Claude进行NLU
            extracted = await self._extract_with_claude(result['snippet'])
            
            structured.append({
                **result,
                'extracted_data': extracted
            })
        
        return structured
    
    async def _extract_with_claude(self, text: str) -> Dict:
        """使用Claude进行信息提取"""
        message = self.claude_client.messages.create(
            model='claude-3-5-sonnet-20241022',
            max_tokens=500,
            messages=[
                {
                    'role': 'user',
                    'content': f'''
请从以下文本中提取关键信息，返回JSON格式：

文本: "{text}"

提取以下内容（如果存在）：
- company_name: 企业名称
- key_info: 关键信息
- numbers: 数字数据
- date: 信息时间

返回格式: {{"company_name": "...", "key_info": "...", ...}}
                    '''
                }
            ]
        )
        
        try:
            import json
            return json.loads(message.content[0].text)
        except:
            return {'raw_text': text}
    
    def calculate_quality_scores(
        self,
        items: List[Dict]
    ) -> List[Dict]:
        """计算质量评分"""
        
        for item in items:
            score = 50  # 基础分
            
            # 来源权威性
            source_credibility = self.config['sources'].get(
                item['source_name'], {}
            ).get('credibility_score', 70)
            score += (source_credibility / 100) * 30  # 权重30%
            
            # 多源验证
            num_sources = len(item.get('sources', []))
            if num_sources >= 3:
                score += 20
            elif num_sources >= 2:
                score += 15
            
            # 信息新鲜度
            days_old = self._calculate_days_old(item.get('timestamp'))
            if days_old <= 30:
                score += 10
            elif days_old <= 90:
                score += 5
            
            item['quality_score'] = min(100, max(0, int(score)))
            item['quality_grade'] = 'A' if score >= 80 else 'B' if score >= 60 else 'C'
        
        return items
    
    def _is_advertisement(self, text: str) -> bool:
        """检查是否是广告"""
        ad_keywords = ['广告', '推广', '赞助', '商业信息']
        return any(kw in text for kw in ad_keywords)
    
    def _is_error_page(self, url: str) -> bool:
        """检查是否是错误页面"""
        error_patterns = ['404', '502', '503', 'error']
        return any(pattern in url.lower() for pattern in error_patterns)
    
    def _calculate_days_old(self, timestamp: str) -> int:
        """计算信息年龄（天数）"""
        from datetime import datetime
        try:
            item_date = datetime.fromisoformat(timestamp)
            days = (datetime.now() - item_date).days
            return days
        except:
            return 999
```

---

## 第四部分：使用示例

### 4.1 基本使用

```bash
# 采集单个企业
python scripts/collect_company.py --companies 格林美 --quality-threshold 70

# 采集多个企业的特定维度
python scripts/collect_company.py \
  --companies 格林美 邦普 光华科技 \
  --dimensions 经营现状 战略规划 \
  --output data/results_2024.json

# 降低质量阈值以获取更多数据
python scripts/collect_company.py \
  --companies 格林美 \
  --quality-threshold 50 \
  --output data/all_data.json
```

### 4.2 编程调用

```python
# 在Python代码中调用

import asyncio
from scripts.collect_company import CompanyCollector

async def main():
    collector = CompanyCollector(config_path='config.yaml')
    
    results = await collector.collect(
        companies=['格林美', '邦普'],
        dimensions=['经营现状', '战略规划'],
        quality_threshold=75
    )
    
    # 处理结果
    print(f"采集完成，共获得 {results['statistics']['high_quality']} 条高质量数据")
    
    # 访问数据
    for item in results['data']:
        print(f"{item['company']}: {item['key']}")

asyncio.run(main())
```

### 4.3 定时采集任务

```python
# scripts/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from collect_company import CompanyCollector
import asyncio

scheduler = BackgroundScheduler()

def scheduled_collect():
    """定时采集任务"""
    collector = CompanyCollector()
    result = asyncio.run(
        collector.collect(
            companies=['格林美', '邦普', '光华科技'],
            dimensions=['经营现状', '战略规划'],
            quality_threshold=70
        )
    )
    print(f"定时采集完成: {result['statistics']}")

# 每周一上午10点执行采集
scheduler.add_job(scheduled_collect, 'cron', day_of_week=0, hour=10)

scheduler.start()
```

---

**下一步推荐阅读**：[08_Claude集成和深度分析.md](08_Claude集成和深度分析.md)
