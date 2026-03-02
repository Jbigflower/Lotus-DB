## 一、概述

Model 层是系统的数据结构核心，承担**数据定义、输入输出验证、数据库映射、分页结构封装**等职责。  
它贯穿整个系统的数据流转过程，从 API 请求到数据库操作，再到最终响应输出。

Model 层的设计目标是：

- 保证各层之间的数据边界清晰；
    
- 实现输入输出的数据安全与类型约束；
    
- 提高可维护性和可扩展性。
    

---

## 二、Model 层结构

Model 层定义了五类核心模型，每类模型都有明确的职责和使用场景：

|模型类型|示例|作用说明|
|---|---|---|
|**Base**|`UserBase`|通用字段定义，供其他模型继承|
|**InDB**|`UserInDB`|数据库存储模型，包含数据库层字段|
|**Create**|`UserCreate`|创建数据时的输入模型|
|**Update**|`UserUpdate`|更新数据时的输入模型|
|**Read**|`UserRead`|数据读取与响应输出模型|
|**PageResult**|`UserPage`|分页响应模型，封装分页元数据|

---

## 三、模型职责详解

### 1. `Base` 模型 —— 通用字段定义

- 定义实体共有字段（如 `id`、`created_at`、`updated_at`）。
    
- 只承担数据结构定义，不包含业务逻辑。
    

**示例：**

```python
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
	email: EmailStr = Field(..., description="邮箱")
```

---

### 2. `InDB` 模型 —— 数据库存储结构

- 表示数据库中的实际存储字段；
    
- 通常直接对应数据库文档或表结构；
    
- 仅在 **Repo 层内部** 使用，不直接返回给上层。
    

**示例：**

```python
class UserInDB(UserBase):
    hashed_password: str = Field(..., description="加密密码")
```

---

### 3. `Create` 模型 —— 创建请求模型

- 用于 **Router / Service / Logic 层** 的创建输入校验；如果使用依赖注入，那么需要使用`CreateScheme` 与 `Create` 分离，比如通过 `get_current_user` 获取当前用户id，那么`CreateScheme`便无须包含 `user_id` 字段。
    
- 仅包含允许在创建时写入的字段；
    
- 不包含系统自动生成字段（如 `id`、`created_at`）。
    

**示例：**

```python
class UserCreate(UserBase):
    password: str = Field(..., min_length=6, description="明文密码")
```

---

### 4. `Update` 模型 —— 更新请求模型

- 用于 **Router / Logic / Repo 层** 的部分更新；
    
- 所有字段都是可选的；
    
- 不允许更新只读字段（例如 `id`、`created_at`）。
    

**示例：**

```python
class UserUpdate(UserBase):
	username: Optional[str] = Field(None, min_length=3, max_length=50, description="用户名")
	email: Optional[EmailStr] = Field(None, description="邮箱")
```

---

### 5. `Read` 模型 —— 响应输出模型

- 定义返回给前端或调用方的字段；
    
- **不包含敏感信息**（如密码哈希）；
    
- 通常由 Logic 或 Repo 层通过 `model_validate()` 从 `InDB` 转换生成。
    

**示例：**

```python
class UserRead(BaseModel):
	id: str = Field(..., description="用户ID")
	last_login_at: Optional[datetime] = Field(None, description="最后登录时间")
	created_at: datetime = Field(..., description="创建时间")
	updated_at: datetime = Field(..., description="更新时间")
```

---

### 6. `PageResult` 模型 —— 分页结果封装

- 用于统一分页响应结构；
    
- 支持泛型化定义，提高可重用性；
    
- 返回总数、页码及结果集。
    

**示例：**

```python
from typing import Generic, List, TypeVar
T = TypeVar("T")

class PageResult(BaseModel, Generic[T]):
    items: List[UserRead] = Field(default_factory=list, description="用户列表")
```

---

## 四、在系统分层中的作用

Model 层在系统结构中处于核心位置，贯穿五个主要层级：

```
┌──────────┐
│  Router  │  → 使用 Create / Update 进行输入校验，返回 Read / PageResult
├──────────┤
│  Service │  → 调用 Logic，附加 user_id、日志、后台任务
├──────────┤
│  Logic   │  → 使用 Create / Update 校验，返回 Read / PageResult
├──────────┤
│  Repo    │  → 使用 Create / Update 操作数据库，返回 InDB / Read
├──────────┤
│   DB     │  → 持久化数据，映射 InDB 模型结构
└──────────┘
```

### 层间模型流转说明：

|层级|输入模型|输出模型|说明|
|---|---|---|---|
|**Router**|Create / Update|Read / PageResult|请求参数与响应验证|
|**Service**|Create / Update|Read / PageResult|添加 user_id、日志与任务|
|**Logic**|Create / Update|Read / PageResult|业务逻辑与规则校验|
|**Repo**|Create / Update|InDB / Read / PageResult|与数据库交互|
|**DB**|InDB|-|存储与查询|

---

## 五、设计原则

1. **单一职责原则**  
    每类模型只处理自己职责范围内的字段。
    
2. **输入输出严格分离**  
    Create/Update 负责写入；Read 负责输出；InDB 仅供内部使用。
    
3. **安全性优先**  
    输出模型不得包含敏感字段（如密码、密钥、Token）。
    
4. **一致性约束**  
    所有模块均遵循统一命名规范与字段类型定义。
    
5. **可扩展性**  
    Model 层支持泛型与继承，便于快速扩展新实体。
    

---

## 六、命名规范

|模型类型|命名约定|示例|
|---|---|---|
|基础模型|`<Entity>Base`|`UserBase`|
|创建模型|`<Entity>Create`|`UserCreate`|
|更新模型|`<Entity>Update`|`UserUpdate`|
|存储模型|`<Entity>InDB`|`UserInDB`|
|响应模型|`<Entity>Read`|`UserRead`|
|分页模型|`<Entity>Page`|`UserPage`|
