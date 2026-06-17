#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Exir System - Enterprise-Grade Schemas Contract (Pydantic V2 - Thread-Safe & Precise)
======================================================================================
هاب مرکزی قراردادهای داده‌ای سامانه اکسیرپویان.
طراحی شده با استانداردهای ساخت‌یافته متناسب با پایگاه‌داده PostgreSQL و Directus BaaS.
این فایل تنها مرجع تایید اصالت کدهای ورودی و خروجی در تمام ماژول‌ها است.
"""

from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Literal, Generic, TypeVar, Annotated
from uuid import UUID, uuid4
import re
import threading

from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    field_validator,
    field_serializer,
    model_validator,
    EmailStr,
    BeforeValidator,
)
import jdatetime

# ---------------------------------------------------------------------------
# عبارات منظم پیش‌کامپایل شده جهت ارزیابی الگوها با حداکثر کارایی
# ---------------------------------------------------------------------------
SHAMSI_DATE_RE = re.compile(r"^(1[34]\d{2})/(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])$")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{3,30}$")
PLUGIN_ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
MESC_CODE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$|^\d{10}$")  # استاندارد کدهای متریال صنعت نفت

T = TypeVar("T")


# ===========================================================================
# خطاهای اختصاصی فرآیندها (Business Logic Custom Exceptions)
# ===========================================================================

class TemporalValidationError(ValueError):
    """کلاس خطای اختصاصی زمان‌بندی برای مهار تداخلات ددلاین‌ها در تست‌ها"""
    pass


# ===========================================================================
# مبدل‌های پیش‌پردازشگر داده‌های ورودی فرانت‌اند (UI Lax-Input Coercion Gateways)
# ===========================================================================

def empty_str_to_none(value: Any) -> Any:
    """تبدیل رشته‌های خالی فرم‌های وب به None جهت ممانعت از کرش کردن اعتبارسنجی Strict"""
    if isinstance(value, str):
        cleaned = value.strip()
        return None if cleaned == "" else cleaned
    return value

# تعریف انواع داده با قابلیت تصفیه خودکار ورودی‌های فرم کلاینت (NiceGUI)
LaxUUID = Annotated[UUID, BeforeValidator(empty_str_to_none)]
LaxOptionalUUID = Annotated[Optional[UUID], BeforeValidator(empty_str_to_none)]
LaxOptionalStr = Annotated[Optional[str], BeforeValidator(empty_str_to_none)]
LaxOptionalDecimal = Annotated[Optional[Decimal], BeforeValidator(empty_str_to_none)]
LaxOptionalDate = Annotated[Optional[date], BeforeValidator(empty_str_to_none)]


# ===========================================================================
# لایه گیت‌وی تاریخ (The Date Gateway - Jalali <-> Gregorian Core Helpers)
# ===========================================================================

def shamsi_to_gregorian(shamsi_str: str) -> date:
    """تبدیل تاریخ شمسی به شیء میلادی با بررسی کامل سال‌های کبیسه و تعداد روزهای ماه‌ها"""
    if not shamsi_str:
        raise ValueError("رشته تاریخ نمی‌تواند خالی باشد.")
    
    clean_str = re.sub(r'[^\d/]', '', shamsi_str).strip()
    if not SHAMSI_DATE_RE.match(clean_str):
        raise ValueError("فرمت تاریخ شمسی نامعتبر است. فرمت صحیح: YYYY/MM/DD")
        
    parts = clean_str.split('/')
    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    
    try:
        # واگذاری کامل کنترل محدوده ماه‌ها، روزها و سال‌های کبیسه به موتور بومی jdatetime
        return jdatetime.date(year, month, day).togregorian()
    except ValueError as e:
        raise ValueError(f"تاریخ جلالی وارد شده معتبر نیست: {str(e)}")

def gregorian_to_shamsi(greg_date: date) -> str:
    """تبدیل شیء تاریخ میلادی به رشته تاریخ شمسی استاندارد YYYY/MM/DD"""
    if not isinstance(greg_date, (date, datetime)):
        raise ValueError("ورودی باید از نوع تاریخ میلادی باشد.")
    j_date = jdatetime.date.fromgregorian(date=greg_date)
    return f"{j_date.year:04d}/{j_date.month:02d}/{j_date.day:02d}"


# ===========================================================================
# رجیستری پویا و توسعه‌پذیر حالات و وضعیت‌های فرآیندی (Open-Closed Principle Registries)
# ===========================================================================

class StateRegistry:
    """
    ثبت‌کننده پویا و نخ‌امن وضعیت‌های فرآیندی.
    طراحی شده با قفل متقابل جهت تضمین پایداری تراکنش‌های همزمان در محیط‌های چندپردازشی (Multi-Worker).
    """
    _lock = threading.Lock()
    
    WORK_ORDER_STATES = {
        "DRAFT", "PLANT_MANAGER_REVIEW", "CEO_INITIAL_REVIEW", "HSE_REVIEW",
        "ENGINEERING_REVIEW", "EXECUTOR_REVIEW", "WAREHOUSE_REVIEW",
        "CEO_FINAL_REVIEW", "APPROVED", "REJECTED", "LEGACY_OR_UNKNOWN"
    }
    
    TASK_ORDER_STATES = {
        "CREATED", "ENG_REVIEW", "HSE_REVIEW", "IN_PROGRESS", "QC_CHECK", "COMPLETED", "CANCELLED", "LEGACY_OR_UNKNOWN"
    }
    
    ACTIVITY_TYPES = {
        "MECHANICAL_PIPING", "ELECTRICAL_INSTRUMENT", "CIVIL_CONSTRUCTION",
        "INSULATION_SCAFFOLDING", "WELDING_FABRICATION", "IT_SOFTWARE", "NON_PRODUCTION_SERVICES"
    }
    
    WORK_NATURES = {
        "PM", "EM", "PROJECT_DEVELOPMENT", "GENERAL_SUPPORT"
    }
    
    HANDOVER_STATUSES = {
        "FULLY_COMPLETED", "UNFINISHED_SUSPENDED", "CANCELLED"
    }

    @classmethod
    def register_work_order_state(cls, state: str) -> None:
        with cls._lock:
            cls.WORK_ORDER_STATES.add(state)

    @classmethod
    def register_task_order_state(cls, state: str) -> None:
        with cls._lock:
            cls.TASK_ORDER_STATES.add(state)

    @classmethod
    def register_activity_type(cls, activity: str) -> None:
        with cls._lock:
            cls.ACTIVITY_TYPES.add(activity)


# ===========================================================================
# اسکیماهای پایه و فونداسیون حسابرسی دایرکتوس (Base Contracts & Audit Foundations)
# ===========================================================================

class BaseContractModel(BaseModel):
    """مدل پایه سخت‌گیرانه برای تضمین انطباق متغیرها و رفتارهای همسان"""
    model_config = ConfigDict(
        strict=True,
        from_attributes=True,
        populate_by_name=True,
        validate_assignment=True,
        extra="forbid"
    )

class BaseAuditModel(BaseContractModel):
    """
    سنگ بنای حسابرسی سازگار با Directus BaaS و جداول DDL پایگاه داده پستگرس.
    تمام فیلدهای حسابرسی دایرکتوس، پیوست‌های سراسری و متادیتاهای منعطف به این کلاس منتقل شده‌اند.
    سازگار با استانداردهای پایتون ۳.۱۲ و ممانعت از هشدارهای منسوخ شدن متد تاریخ در پس‌زمینه.
    """
    attachments: List[UUID] = Field(default_factory=list, description="لیست شناسه‌های فایل‌های آپلود شده در سیستم دایرکتوس")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="ساختار جی‌سان منعطف برای متغیرهای پیش‌بینی نشده")
    date_created: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="تاریخ ایجاد رکورد")
    date_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="تاریخ ویرایش رکورد")
    user_created: Optional[UUID] = Field(None, description="کاربر ایجاد کننده رکورد")
    user_updated: Optional[UUID] = Field(None, description="کاربر ویرایش کننده رکورد")
    is_deleted: bool = Field(default=False, description="حذف منطقی نرم رکورد")


# ===========================================================================
# اسکیماهای اطلاعات مرجع سیستمی (Reference Core Schemas)
# ===========================================================================

class UserSchema(BaseAuditModel):
    """قرارداد کاربری متصل به هویت کاربران Directus BaaS"""
    id: UUID = Field(default_factory=uuid4)
    username: str = Field(..., description="نام کاربری منحصر‌به‌فرد سیستم")
    full_name: str = Field(..., min_length=3, max_length=100, description="نام و نام خانوادگی پرسنل")
    email: EmailStr = Field(..., description="ایمیل سازمانی کاربر")
    department: str = Field(..., min_length=2, description="واحد سازمانی (مانند برق، مکانیک)")
    role: str = Field(..., description="نقش سیستمی بازخوانی شده از دایرکتوس")
    is_active: bool = Field(default=True)
    external_ids: Dict[str, str] = Field(default_factory=dict, description="نگاشت شناسه‌های اودوو و ویکنها")

    @field_validator("username")
    @classmethod
    def validate_username_format(cls, val: str) -> str:
        if not USERNAME_RE.match(val):
            raise ValueError("نام کاربری نامعتبر است. فرمت مجاز: حروف، اعداد و کاراکترهای _ - .")
        return val

class AssetSchema(BaseAuditModel):
    """قرارداد تجهیزات سایت (Asset List) جهت ارجاعات آتی ساختار نگهداری و تعمیرات"""
    id: UUID = Field(default_factory=uuid4)
    asset_code: str = Field(..., description="کد منحصر‌به‌فرد یا Tag Number تجهیز")
    asset_name: str = Field(..., min_length=2, description="نام تجهیز فنی")
    location: LaxOptionalStr = Field(None, description="موقعیت استقرار فیزیکی تجهیز")
    parent_id: LaxOptionalUUID = Field(None, description="شناسه تجهیز بالادستی در درختواره تجهیزات")


# ===========================================================================
# ۱. ساختارهای صورتجلسه به عنوان مرجع کار (Meeting Minutes Contracts)
# ===========================================================================

class MeetingItemSchema(BaseAuditModel):
    """قرارداد بند مصوبات صورتجلسه؛ مجهز به فیلدهای تجمعی بررسی وضعیت پیشرفت تسک‌ها با دقت عددی بالا"""
    id: UUID = Field(default_factory=uuid4)
    meeting_id: UUID = Field(..., description="شناسه هدر صورتجلسه والد")
    item_number: int = Field(..., ge=1, description="شماره بند مصوبه در صورتجلسه")
    description: str = Field(..., min_length=5, description="متن کامل مصوبه اجرایی")
    deadline: LaxOptionalDate = Field(None, description="مهلت تعیین‌شده جهت اجرای کار")
    
    # فیلدهای محاسباتی تجمعی پیشرفت با دقت عددی اعشاری استاندارد
    aggregate_status: str = Field(default="PENDING", description="وضعیت تجمیعی بر اساس تسک‌ها (PENDING, IN_PROGRESS, COMPLETED)")
    resolved_percentage: Decimal = Field(default=Decimal("0.0"), ge=Decimal("0.0"), le=Decimal("100.0"), description="درصد پیشرفت کارگاهی تسک‌های مرتبط")

    @field_serializer("deadline")
    def serialize_deadline(self, value: Optional[date]) -> Optional[str]:
        if value is None:
            return None
        return gregorian_to_shamsi(value)

class MeetingMinutesHeaderSchema(BaseAuditModel):
    """قرارداد هدر صورتجلسات مراجع کار؛ با پیوند یکپارچه حضور افراد از طریق جدول واسط"""
    id: UUID = Field(default_factory=uuid4)
    meeting_number: Optional[str] = Field(None, description="شماره رسمی صورتجلسه؛ در زمان ایجاد ارسال نمی‌شود تا دیتابیس بومی آن را تولید کند")
    title: str = Field(..., min_length=5, max_length=250, description="موضوع یا عنوان جلسه")
    shamsi_date: str = Field(..., description="تاریخ برگزاری جلسه به شمسی (YYYY/MM/DD)")
    attendees: List[UUID] = Field(..., min_length=1, description="لیست شناسه پرسنل حاضر در جلسه (M2M)")
    items: List[MeetingItemSchema] = Field(default_factory=list, description="لیست مصوبات صورتجلسه")

    @field_validator("shamsi_date")
    @classmethod
    def validate_meeting_date(cls, value: str) -> str:
        try:
            shamsi_to_gregorian(value)
            return value
        except Exception as e:
            raise ValueError(f"تاریخ برگزاری نامعتبر است: {str(e)}")


# ===========================================================================
# ۲. ساختار درخواست شروع کار - ورک‌اوردر (Work Order Contracts)
# ===========================================================================

class WorkOrderSchema(BaseAuditModel):
    """
    قرارداد فرآیندی درخواست شروع کار؛ هماهنگ با استانداردهای فیلدهای پیش‌فرض دایرکتوس
    و مجهز به استیت ماشین تاییدات به همراه پیش‌پردازشگرهای ورودی فرم جهت ممانعت از کرش ساید کلاینت.
    """
    id: UUID = Field(default_factory=uuid4)
    wo_number: Optional[str] = Field(None, description="شماره انحصاری درخواست کار؛ در زمان ایجاد برای ممانعت از تداخل خالی ارسال می‌شود")
    title: str = Field(..., min_length=5, max_length=250, description="عنوان کار درخواستی")
    applicant_id: UUID = Field(..., description="شناسه درخواست‌کننده کار")
    inspector_id: UUID = Field(..., description="شناسه ناظر فنی تعیین‌شده")
    follower_id: UUID = Field(..., description="شناسه کارشناس پیگیری‌کننده")
    
    # بخش ۱: شرح درخواست و فوریت
    request_description: str = Field(..., min_length=5, description="شرح لزوم اجرا و مشکلات عدم انجام کار")
    urgency_level: Literal["NORMAL", "URGENT", "CRITICAL"] = "NORMAL"
    
    # بخش ۲ تا ۸: نظرات و تاییدات فازهای مختلف جریان تایید با لایه انعطاف‌پذیر Lax
    plant_manager_opinion: LaxOptionalStr = None
    plant_manager_approved: Optional[bool] = None
    
    ceo_initial_opinion: LaxOptionalStr = None
    ceo_initial_approved: Optional[bool] = None
    
    hse_notes: LaxOptionalStr = None
    
    engineering_duration_estimate: LaxOptionalStr = None
    engineering_description: LaxOptionalStr = None
    needs_design_or_drawing: bool = False
    engineering_obstacles: LaxOptionalStr = None
    
    executor_duration_estimate: LaxOptionalStr = None
    executor_obstacles: LaxOptionalStr = None
    needs_outsourcing: bool = False
    
    mto_number: LaxOptionalStr = None
    warehouse_stock_status: LaxOptionalStr = None
    
    ceo_final_approved: Optional[bool] = None
    ceo_final_opinion: LaxOptionalStr = None
    ceo_final_outsourcing_needed: Optional[bool] = None
    
    # مدیریت وضعیت (کنترل شده بر اساس رجیستری پویا)
    current_state: str = Field(default="DRAFT", description="وضعیت جاری سند در ماشین حالت")

    @field_validator("current_state")
    @classmethod
    def validate_state_ocp(cls, val: str) -> str:
        # ممانعت از کرش دیسریالیز در اثر از کار افتادن پلاگین‌ها
        if val not in StateRegistry.WORK_ORDER_STATES:
            return "LEGACY_OR_UNKNOWN"
        return val

    @model_validator(mode="after")
    def validate_state_machine_integrity(self) -> "WorkOrderSchema":
        """اعتبارسنجی متقاطی دقیق جهت ممانعت از پرش وضعیت بدون ثبت تاییدهای مربوطه"""
        state = self.current_state

        # ۱. در صورت مخالفت هر یک از مراجع در هر مرحله، وضعیت کل ورک‌اوردر باید REJECTED باشد
        if self.plant_manager_approved is False or self.ceo_initial_approved is False or self.ceo_final_approved is False:
            if state != "REJECTED":
                raise ValueError("با توجه به ثبت عدم تایید توسط یکی از مراجع صالحه، وضعیت ورک‌اوردر باید حتماً REJECTED باشد.")

        # ۲. پیش‌نویس نباید اطلاعات تایید مراجع را در خود داشته باشد
        if state == "DRAFT":
            if any([self.plant_manager_approved, self.ceo_initial_approved, self.ceo_final_approved]):
                raise ValueError("ورک‌اوردر پیش‌نویس نباید تاییدیه ثبت شده داشته باشد.")

        # ۳. حرکت در وضعیت‌های ماشین حالت مستلزم احراز تاییدات مراحل قبلی است
        if state == "CEO_INITIAL_REVIEW":
            if self.plant_manager_approved is not True:
                raise ValueError("برای ورود به مرحله تایید اولیه مدیرعامل، ثبت تایید مدیر کارخانه الزامی است.")
        
        elif state in ("HSE_REVIEW", "ENGINEERING_REVIEW", "EXECUTOR_REVIEW", "WAREHOUSE_REVIEW", "CEO_FINAL_REVIEW"):
            if self.plant_manager_approved is not True or self.ceo_initial_approved is not True:
                raise ValueError("برای ورود به مراحل میانی گردش کار، اخذ تایید مدیر کارخانه و تایید اولیه مدیرعامل الزامی است.")
                
        elif state == "APPROVED":
            if not (self.plant_manager_approved is True and self.ceo_initial_approved is True and self.ceo_final_approved is True):
                raise ValueError("تغییر وضعیت به APPROVED تنها در صورت اخذ کامل تاییدات مدیر کارخانه، تایید اولیه و تایید نهایی مدیرعامل میسر است.")
                
        return self


# ===========================================================================
# ۳. ساختار درخواست کار اضطراری/متفرقه (Emergency Work Contracts)
# ===========================================================================

class EmergencyRequestSchema(BaseAuditModel):
    """قرارداد درخواست کارهای غیرمنتظره و فوری خارج از فرآیند ورک‌اوردر"""
    id: UUID = Field(default_factory=uuid4)
    emergency_number: Optional[str] = Field(None, description="شماره پیگیری درخواست اضطراری؛ در زمان ایجاد جهت واگذاری به سکوئنس ارسال نمی‌شود")
    title: str = Field(..., min_length=5, description="عنوان شرایط اضطراری")
    description: str = Field(..., min_length=5, description="شرح نقص فنی رخ‌داده")
    requestor_unit: str = Field(..., description="واحد عملیاتی متقاضی کار اضطراری")
    safety_precautions: str = Field(..., description="اقدامات ایمنی فوری اتخاذ شده در محل")
    approved_by: UUID = Field(..., description="شناسه سرپرست صادرکننده تاییدیه اضطراری")


# ===========================================================================
# ۴. ساختار دستور کار تفکیکی - تسک‌اوردر (Task Order Contracts)
# ===========================================================================

class TaskOrderSchema(BaseAuditModel):
    """قرارداد دستور کارهای تفکیکی؛ مجهز به پیش‌پردازشگرهای منعطف ورودی جهت یکپارچه‌سازی آسان با فرم‌های وب"""
    id: UUID = Field(default_factory=uuid4)
    to_number: Optional[str] = Field(None, description="شماره دستور کار تفکیکی؛ در زمان ایجاد جهت واگذاری به سکوئنس نادیده گرفته می‌شود")
    title: str = Field(..., min_length=5, description="عنوان کار اجرایی تفکیکی")
    inspector_id: UUID = Field(..., description="شناسه ناظر کارگاه")
    
    # ارجاع اختیاری به اسناد منشأ والد با استفاده از Lax UUID
    parent_work_order_id: LaxOptionalUUID = Field(None, description="شناسه ورک‌اوردر مرجع")
    parent_meeting_item_id: LaxOptionalUUID = Field(None, description="بند مصوبه صورتجلسه مرجع")
    parent_emergency_id: LaxOptionalUUID = Field(None, description="درخواست کار اضطراری مرجع")
    
    # الزامات و نظریات واحدهای هماهنگ‌کننده
    engineering_requirements: LaxOptionalStr = Field(None, description="الزامات و شرح فعالیت مهندسی")
    engineering_documents: LaxOptionalStr = Field(None, description="لیست مدارک و نقشه‌های ضمیمه")
    mto_reference_number: LaxOptionalStr = Field(None, description="کد مرجع MTO کالا")
    required_materials: LaxOptionalStr = Field(None, description="اقلام مورد نیاز و اقدامات پیش‌نیاز")
    estimated_execution_time: LaxOptionalStr = Field(None, description="زمان برآورد شده جهت اتمام کار")
    
    hse_requirements: LaxOptionalStr = Field(None, description="الزامات ایمنی و ملاحظات عملیاتی واحد HSE")
    execution_description_and_obstacles: LaxOptionalStr = Field(None, description="شرح اقدامات کارگاهی و موانع")
    
    # تاییدات پایانی تسک‌اوردر
    qc_inspector_id: LaxOptionalUUID = Field(None, description="شناسه ناظر کنترل کیفیت (QC)")
    requester_approver_id: LaxOptionalUUID = Field(None, description="شناسه تحویل‌گیرنده نهایی کار")
    
    # اطلاعات تحویل موقت نقشه ازبیلت
    as_built_creator_id: LaxOptionalUUID = Field(None, description="تهیه‌کننده نقشه چون‌ساخت")
    as_built_drawing_number: LaxOptionalStr = Field(None, description="شماره ثبت نقشه ازبیلت")
    handover_minutes_reference: LaxOptionalStr = Field(None, description="کد بایگانی صورتجلسه فیزیکی تحویل")
    
    # وضعیت ماشین حالت تسک‌اوردر (تطبیق با رجیستری پویا)
    current_state: str = Field(default="CREATED", description="وضعیت جاری تسک")

    @field_validator("current_state")
    @classmethod
    def validate_task_state_ocp(cls, val: str) -> str:
        # ممانعت از کرش دیسریالیز در اثر از کار افتادن پلاگین‌ها
        if val not in StateRegistry.TASK_ORDER_STATES:
            return "LEGACY_OR_UNKNOWN"
        return val

    @model_validator(mode="after")
    def validate_parent_reference_exclusivity(self) -> "TaskOrderSchema":
        """اعتبارسنجی انحصاری بودن ارجاع؛ کار باید حتماً حداقل یک والد مرجع داشته باشد"""
        parents = [self.parent_work_order_id, self.parent_meeting_item_id, self.parent_emergency_id]
        if self.current_state != "CREATED":
            if not any(parents):
                raise ValueError("هر دستور کار تفکیکی فعال باید حتماً به یک سند مرجع (والد) متصل باشد.")
        return self


# ===========================================================================
# ۵. ساختار تحویل کار و موازنه کالا (Handover & Material Balance Contracts)
# ===========================================================================

class MaterialBalanceSchema(BaseAuditModel):
    """
    قرارداد اقلام مصرفی و موازنه کالا مبتنی بر کلاس پردازشی Decimal با دقت بسیار بالا.
    بهره‌گیری از Decimal از خطاهای ممیز شناور (مانند 0.1 + 0.2 = 0.3000000004) جلوگیری می‌کند.
    """
    id: UUID = Field(default_factory=uuid4)
    handover_id: UUID = Field(..., description="شناسه فرم تحویل کار مربوطه")
    item_code_mesc: str = Field(..., description="کد استاندارد کالا (کد ۱۰ رقمی یا MESC)")
    item_description: str = Field(..., min_length=2, description="شرح کالا مطابق با کاتالوگ انبار")
    unit_of_measure: str = Field(..., description="واحد سنجش کالا (عدد، متر، کیلوگرم)")
    
    # فیلدهای محاسباتی موازنه جرمی کالا مبتنی بر ساختار عددی Decimal جهت کنترل مالی سخت‌گیرانه
    qty_received_warehouse: Decimal = Field(..., ge=Decimal("0.0"), description="مقدار دریافتی از انبار طبق حواله")
    qty_actual_used: Decimal = Field(..., ge=Decimal("0.0"), description="مقدار واقعی مصرف شده در تجهیز")
    qty_returned_warehouse: Decimal = Field(default=Decimal("0.0"), ge=Decimal("0.0"), description="مقدار مرجوع شده به انبار")
    qty_waste: Decimal = Field(default=Decimal("0.0"), ge=Decimal("0.0"), description="مقدار پرت یا ضایعات غیرقابل استفاده")
    
    return_receipt_number: LaxOptionalStr = Field(None, description="شماره سند برگشت به انبار (رسید برگشتی)")

    @field_validator("item_code_mesc")
    @classmethod
    def validate_mesc_code(cls, val: str) -> str:
        if not MESC_CODE_RE.match(val):
            raise ValueError("کد کالا نامعتبر است. فرمت صحیح: کد ۱۰ رقمی یا ساختار XX.XX.XXXX")
        return val


class QualityChecklistSchema(BaseAuditModel):
    """قرارداد سوالات پنج‌گانه بازرسی انضباط کارگاهی و کیفیت نهایی"""
    id: UUID = Field(default_factory=uuid4)
    handover_id: UUID = Field(..., description="شناسه فرم تحویل کار")
    question_index: int = Field(..., ge=1, le=5, description="ردیف شاخص کنترلی")
    status: Literal["YES", "NO", "N/A"] = Field(..., description="وضعیت تایید شاخص")


class WorkHandoverSchema(BaseAuditModel):
    """
    قرارداد جامع فرم تحویل کار، تجمیع‌کننده تسک‌اوردر، چک‌لیست و موازنه کالا.
    موازنه جرمی کالا در زمان نهایی‌سازی (FULLY_COMPLETED) به صورت کاملاً ریاضی و انطباق مطلق (بدون هیچ تلورانسی) بررسی می‌شود.
    """
    id: UUID = Field(default_factory=uuid4)
    handover_number: Optional[str] = Field(None, description="شماره رسمی تحویل کار؛ در زمان ایجاد جهت واگذاری به سکوئنس نادیده گرفته می‌شود")
    task_order_id: UUID = Field(..., description="شناسه دستور کار تفکیکی خاتمه‌یافته")
    
    # اطلاعات مجوز کار (HSE Permit)
    permit_number: str = Field(..., description="شماره مجوز کار گرم/سرد فیزیکی")
    permit_issuer_id: UUID = Field(..., description="صادرکننده مجوز کار")
    permit_receiver_id: UUID = Field(..., description="تحویل‌گیرنده مجوز کار")
    permit_hse_inspector_id: UUID = Field(..., description="ناظر ایمنی تاییدکننده کار در سایت")
    warehouse_requisition_numbers: List[str] = Field(..., min_length=1, description="لیست شماره حواله درخواست کالا از انبار")
    
    # طبقه‌بندی (تطبیق پویا با رجیستری)
    activity_type: str = Field(..., description="واحد فعال صادر کننده")
    work_nature: str = Field(..., description="ماهیت و طبقه‌بندی فعالیت")
    
    # کنترل زمان‌بندی و موازنه
    final_status: str = Field(default="FULLY_COMPLETED", description="وضعیت نهایی اجرای تسک")
    delay_reason: LaxOptionalStr = Field(None, description="علت تاخیر یا عدم تکمیل کار در صورت وجود")
    material_deviation_reason: LaxOptionalStr = Field(None, description="علت اختلاف متریال واقعی از MTO اولیه")
    additional_remarks: LaxOptionalStr = None
    
    # اسناد ضمیمه تاییدهای کیفی و موازنه
    checklist_entries: List[QualityChecklistSchema] = Field(..., min_length=5, description="چک‌لیست پنج شاخص کیفی")
    materials_balances: List[MaterialBalanceSchema] = Field(default_factory=list, description="اقلام مصرفی و برگشتی")
    
    # تاییدکنندگان نهایی سند موازنه و اتمام کار
    execution_supervisor_id: UUID = Field(..., description="امضای سرپرست تیم اجرایی")
    final_receiver_id: UUID = Field(..., description="امضای تحویل‌گیرنده نهایی متقاضی")
    planning_expert_id: UUID = Field(..., description="امضای نهایی کارشناس برنامه‌ریزی جهت بستن پرونده")

    @field_validator("activity_type")
    @classmethod
    def validate_activity_type_ocp(cls, val: str) -> str:
        if val not in StateRegistry.ACTIVITY_TYPES:
            raise ValueError(f"نوع فعالیت '{val}' در چارت سازمانی یا پلاگین‌ها تعریف نشده است.")
        return val

    @field_validator("work_nature")
    @classmethod
    def validate_work_nature_ocp(cls, val: str) -> str:
        if val not in StateRegistry.WORK_NATURES:
            raise ValueError(f"ماهیت فعالیت '{val}' غیرمجاز است.")
        return val

    @field_validator("final_status")
    @classmethod
    def validate_final_status_ocp(cls, val: str) -> str:
        if val not in StateRegistry.HANDOVER_STATUSES:
            raise ValueError(f"وضعیت تحویل '{val}' نامعتبر است.")
        return val

    @model_validator(mode="after")
    def validate_handover_finalization_rules(self) -> "WorkHandoverSchema":
        """اعتبارسنجی موازنه متریال و چک‌لیست فقط و فقط در زمان نهایی‌سازی کار (FULLY_COMPLETED)"""
        if self.final_status == "FULLY_COMPLETED":
            # ۱. چک‌لیست کیفی در زمان نهایی‌سازی حتما باید شامل ۵ شاخص تایید شده باشد
            if not self.checklist_entries or len(self.checklist_entries) < 5:
                raise ValueError("برای نهایی‌سازی کار، بررسی و تایید کامل چک‌لیست ۵ شاخصه الزامی است.")
            
            # ۲. بررسی سخت‌گیرانه موازنه جرم انبار برای تک‌تک اقلام خارج شده با انطباق ریاضی دقیق (بدون هیچ تلورانسی)
            for mat in self.materials_balances:
                calculated_sum = mat.qty_actual_used + mat.qty_returned_warehouse + mat.qty_waste
                if mat.qty_received_warehouse != calculated_sum:
                    raise ValueError(
                        f"عدم موازنه کالا در نهایی‌سازی! مجموع مصرف ({mat.qty_actual_used})، مرجوعی ({mat.qty_returned_warehouse}) "
                        f"و ضایعات ({mat.qty_waste}) برای کالای MESC [{mat.item_code_mesc}] با مقدار دریافتی ({mat.qty_received_warehouse}) انطباق ریاضی دقیق ندارد."
                    )
        return self


# ===========================================================================
# ۶. ساختار لاگ‌های پایش و ردپای حسابرسی امنیتی (Audit Logs & Timeline)
# ===========================================================================

class AuditLogSchema(BaseAuditModel):
    """قرارداد لاگ‌های سیستمی جهت ترسیم خط زمان تعاملات (Timeline) مانند Chatter در Odoo"""
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="زمان ثبت رخداد")
    user_id: UUID = Field(..., description="شناسه کاربر ایجادکننده رخداد")
    action_type: Literal["STATE_CHANGE", "COMMENT", "FILE_UPLOAD", "FIELD_UPDATE"]
    entity_type: Literal["WORK_ORDER", "TASK_ORDER", "MEETING_MINUTES", "HANDOVER"]
    entity_id: UUID = Field(..., description="شناسه سند هدف")
    description: str = Field(..., description="شرح متنی رخداد ثبت شده")
    payload_before: Optional[Dict[str, Any]] = Field(None, description="داده قبلی در صورت بروزرسانی")
    payload_after: Optional[Dict[str, Any]] = Field(None, description="داده جدید پس از بروزرسانی")
    attachment_path: LaxOptionalStr = Field(None, description="آدرس فایل پیوست شده در صورت وجود")


# ===========================================================================
# ۷. ساختار مانیفست پلاگین‌های تعمیمی (Odoo-like Plugin Manifest Contracts)
# ===========================================================================

class DBModelExtension(BaseContractModel):
    target_table: str = Field(..., description="نام جدول مرجع در هسته سیستم")
    new_columns: Dict[str, str] = Field(..., description="نگاشت نام ستون جدید به نوع داده SQL")

class DBNewEntity(BaseContractModel):
    table_name: str = Field(..., description="نام جدول جدید اختصاصی افزونه")
    columns: Dict[str, str] = Field(..., description="تعریف ستون‌ها و فیلدهای جدول جدید")

class UIMenuInjection(BaseContractModel):
    menu_title: str = Field(..., description="عنوان منو در سایدبار اصلی")
    route_path: str = Field(..., description="مسیر آدرس صفحه در NiceGUI")
    icon: str = "extension"

class SecurityRoleInjection(BaseContractModel):
    """قرارداد تزریق سطوح دسترسی امنیتی اختصاصی افزونه به هسته سیستم (RBAC)"""
    role_name: str = Field(..., description="نام سطح دسترسی جدید افزونه")
    permissions: List[str] = Field(..., description="فهرست کامل مجوزهای دسترسی تعریف شده برای نقش")

class PluginManifestSchema(BaseAuditModel):
    """قرارداد مانیفست افزونه‌های توسعه‌پذیر؛ تضمین یکپارچگی نصب پلاگین‌های بدون تداخل"""
    plugin_id: str = Field(..., description="شناسه منحصربه‌فرد افزونه (مانند exir.cmms)")
    name: str = Field(..., description="نام تجاری و نمایشی افزونه")
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$", description="ورژن‌دهی با استاندارد SemVer")
    description: LaxOptionalStr = None
    
    db_extensions: List[DBModelExtension] = Field(default_factory=list, description="تغییرات روی جداول موجود هسته")
    db_new_entities: List[DBNewEntity] = Field(default_factory=list, description="جداول جدید ایجاد شده")
    ui_injections: List[UIMenuInjection] = Field(default_factory=list, description="صفحات اضافه شده به منوی NiceGUI")
    security_roles: List[SecurityRoleInjection] = Field(default_factory=list, description="نقش‌های امنیتی الحاقی به هسته")
    active_hooks: List[str] = Field(default_factory=list, description="لیست نقاط اتصال یا هوک‌های مورد نیاز افزونه")
    dependencies: List[str] = Field(default_factory=list, description="پیش‌نیازهای فعال‌سازی پلاگین")

    @field_validator("plugin_id")
    @classmethod
    def validate_plugin_id_namespace(cls, val: str) -> str:
        if not PLUGIN_ID_RE.match(val):
            raise ValueError("شناسه افزونه نامعتبر است. فرمت صحیح: namespace.plugin_name")
        return val


# ===========================================================================
# ۸. قراردادهای موتور تطبیق و ابهام‌زدایی تجمیعی فایل اکسل (Excel Reconciliation)
# ===========================================================================

class ExcelColumnMap(BaseContractModel):
    """قرارداد نگاشت ستون‌های فایل اکسل به فیلدهای معتبر سیستمی"""
    excel_column_name: str = Field(..., min_length=1, description="نام فیزیکی ستون در اکسل")
    system_field_name: Literal["title", "department", "supervisor", "priority", "due_date"] = Field(..., description="فیلد متناظر سیستم")

class ExcelAmbiguityResolve(BaseContractModel):
    """قرارداد تطابق و معادل‌سازی اسامی مبهم تکراری با پرسنل فعال سیستم"""
    original_name: str = Field(..., min_length=1, description="نام مبهم استخراج‌شده از اکسل")
    selected_user_id: UUID = Field(..., description="شناسه کاربر معادل انتخاب شده از دیتابیس")

class ExcelReconciliationPayload(BaseContractModel):
    """قرارداد تجمیعی بارگذاری و پاک‌سازی فایل اکسل پیش از درج تراکنشی در پایگاه داده"""
    raw_rows: List[Dict[str, Any]] = Field(..., min_length=1, description="سطرهای خام استخراج شده")
    column_mappings: List[ExcelColumnMap] = Field(..., min_length=1, description="تنظیمات مپینگ ستون‌ها")
    resolutions: List[ExcelAmbiguityResolve] = Field(default_factory=list, description="تصمیمات رفع ابهام کاربر")

    @field_validator("column_mappings")
    @classmethod
    def prevent_duplicate_column_mappings(cls, values: List[ExcelColumnMap]) -> List[ExcelColumnMap]:
        mapped_fields = [m.system_field_name for m in values]
        if len(mapped_fields) != len(set(mapped_fields)):
            raise ValueError("نگاشت تکراری غیرمجاز است؛ هر فیلد سیستمی حداکثر به یک ستون متصل می‌شود.")
        return values


# ===========================================================================
# ۹. تنظیمات درگاه‌های یکپارچه‌سازی خروجی (Integration Gateway Configs)
# ===========================================================================

class ProviderConfig(BaseContractModel):
    """قرارداد پیکربندی هاب‌های خروجی توزیع تسک‌ها (مانند Odoo, Vikunja)"""
    provider_id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=3, description="نام درگاه")
    type: Literal["odoo", "vikunja", "n8n", "directus", "custom_webhook"]
    connection_params: Dict[str, Any] = Field(..., description="پارامترهای اتصال و توکن‌های اعتبارسنجی")
    execution_strategy: Literal["sync", "async", "background_retry"] = "async"
    priority: int = Field(default=10, ge=1)
    is_active: bool = Field(default=True)
    routing_filter: Optional[Dict[str, Any]] = Field(None, description="فیلترهای توزیع تسک به درگاه مربوطه")


# ===========================================================================
# ۱۰. ساختارهای استاندارد صفحه‌بندی (Unified API Pagination Metadata)
# ===========================================================================

class PaginationMeta(BaseContractModel):
    """متادیتای استاندارد خروجی‌های لیستی جهت بهینه‌سازی جداول فرانت‌اند"""
    total_count: int = Field(..., ge=0, description="تعداد کل رکوردهای موجود")
    current_page: int = Field(..., ge=1, description="صفحه جاری")
    page_size: int = Field(..., ge=1, description="تعداد رکورد در هر صفحه")
    has_next: bool = Field(..., description="نشان‌دهنده وجود صفحه بعدی")
    has_prev: bool = Field(..., description="نشان‌دهنده وجود صفحه قبلی")


class PaginatedData(BaseContractModel, Generic[T]):
    """پکیج داده‌های صفحه‌بندی شده سازگار با انواع قراردادهای داده‌ای سیستم"""
    items: List[T] = Field(..., description="لیست رکوردهای واکشی شده در صفحه جاری")
    pagination: PaginationMeta = Field(..., description="اطلاعات صفحه‌بندی کلاینت")


# ===========================================================================
# ۱۱. بسته‌بندی پاسخ‌های استاندارد خروجی سرویس‌ها (Google-Style Response Wrap)
# ===========================================================================

class APIResponse(BaseContractModel, Generic[T]):
    """بسته‌بندی رسمی خروجی تمام APIهای سیستم جهت یکپارچگی پاسخ کلاینت‌ها"""
    success: bool = Field(..., description="وضعیت موفقیت یا شکست عملیات")
    data: Optional[T] = Field(None, description="بدنه داده خروجی (می‌تواند از نوع ساده یا PaginatedData باشد)")
    error: Optional[Dict[str, Any]] = Field(None, description="شرح خطا در صورت ناموفق بودن درخواست")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="اطلاعات متای زمانی و پردازشی")