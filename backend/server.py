from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
import os
import re
import secrets
import uuid

import bcrypt
import jwt
from PIL import Image
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field

ROOT_DIR = Path(__file__).parent
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
load_dotenv(ROOT_DIR / ".env")

logger = logging.getLogger("studio_voxel")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

JWT_ALGORITHM = "HS256"
JWT_SECRET = os.environ["JWT_SECRET"]
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"].lower()
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

app = FastAPI(title="Studio Voxel CMS API", version="1.0.0")
api_router = APIRouter(prefix="/api")

origins = [item.strip() for item in os.environ.get("CORS_ORIGINS", "*").split(",") if item.strip()]
allow_credentials = origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/api/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def clean_doc(document: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if document is None:
        return None
    result = dict(document)
    result.pop("_id", None)
    result.pop("password_hash", None)
    return result


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or new_id()[:8]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": "admin",
        "type": "access",
        "jti": new_id(),
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def current_admin(request: Request) -> Dict[str, Any]:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token")
        revoked = await db.revoked_tokens.find_one({"jti": payload.get("jti")}, {"_id": 0})
        if revoked:
            raise HTTPException(status_code=401, detail="Session has ended")
        user = await db.users.find_one({"id": payload.get("sub"), "role": "admin"}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="Administrator not found")
        return clean_doc(user) or {}
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Session expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc


async def optional_admin(request: Request) -> Optional[Dict[str, Any]]:
    try:
        return await current_admin(request)
    except HTTPException:
        return None


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginResponse(BaseModel):
    user: UserOut
    access_token: str


class ServicePayload(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    short_description: str = Field(min_length=10, max_length=240)
    description: str = Field(min_length=10, max_length=3000)
    image_url: str = ""
    icon: str = "01"
    order: int = Field(default=0, ge=0, le=999)
    active: bool = True


class ProjectPayload(BaseModel):
    title: str = Field(min_length=2, max_length=140)
    description: str = Field(min_length=10, max_length=3000)
    image_url: str = ""
    category: str = Field(default="Residential", max_length=80)
    year: str = Field(default="2024", max_length=12)
    location: str = Field(default="London, UK", max_length=120)
    featured: bool = False
    order: int = Field(default=0, ge=0, le=999)
    active: bool = True


class GalleryPayload(BaseModel):
    title: str = Field(min_length=2, max_length=140)
    description: str = Field(default="", max_length=500)
    image_url: str = Field(min_length=5, max_length=500)
    category: str = Field(default="Studio", max_length=80)
    alt_text: str = Field(min_length=5, max_length=180)
    order: int = Field(default=0, ge=0, le=999)
    featured: bool = False
    active: bool = True


class SettingsPayload(BaseModel):
    business_name: str = Field(min_length=2, max_length=120)
    tagline: str = Field(min_length=5, max_length=240)
    email: EmailStr
    phone: str = Field(min_length=5, max_length=50)
    whatsapp: str = Field(default="", max_length=50)
    address: str = Field(min_length=5, max_length=240)
    hours: str = Field(min_length=3, max_length=160)
    instagram: str = Field(default="", max_length=300)
    linkedin: str = Field(default="", max_length=300)
    footer_note: str = Field(min_length=5, max_length=240)


class PageContentPayload(BaseModel):
    page: str = Field(min_length=2, max_length=40)
    eyebrow: str = Field(default="", max_length=120)
    headline: str = Field(min_length=5, max_length=240)
    body: str = Field(min_length=10, max_length=2000)
    image_url: str = Field(default="", max_length=500)


class ContactPayload(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    project_type: str = Field(min_length=2, max_length=120)
    message: str = Field(min_length=10, max_length=2500)


class TestimonialPayload(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    role: str = Field(default="", max_length=120)
    company: str = Field(default="", max_length=140)
    quote: str = Field(min_length=10, max_length=1200)
    image_url: str = Field(default="", max_length=500)
    rating: int = Field(default=5, ge=1, le=5)
    featured: bool = False
    order: int = Field(default=0, ge=0, le=999)
    active: bool = True


class BlogPayload(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    excerpt: str = Field(min_length=10, max_length=400)
    content: str = Field(min_length=20, max_length=20000)
    image_url: str = Field(default="", max_length=500)
    author: str = Field(default="Studio Voxel", max_length=120)
    tags: str = Field(default="", max_length=240)
    published: bool = True
    order: int = Field(default=0, ge=0, le=999)
    active: bool = True


class TeamPayload(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    role: str = Field(min_length=2, max_length=140)
    bio: str = Field(default="", max_length=1200)
    image_url: str = Field(default="", max_length=500)
    instagram: str = Field(default="", max_length=300)
    linkedin: str = Field(default="", max_length=300)
    order: int = Field(default=0, ge=0, le=999)
    active: bool = True


class FaqPayload(BaseModel):
    title: str = Field(min_length=4, max_length=240)
    answer: str = Field(min_length=4, max_length=2000)
    category: str = Field(default="General", max_length=80)
    order: int = Field(default=0, ge=0, le=999)
    active: bool = True


async def sorted_items(collection: str, active_only: bool = False, limit: int = 100) -> List[Dict[str, Any]]:
    query = {"active": True} if active_only else {}
    docs = await db[collection].find(query, {"_id": 0}).sort([("order", 1), ("created_at", -1)]).to_list(limit)
    return [clean_doc(doc) for doc in docs if doc]


async def seed_admin() -> None:
    existing = await db.users.find_one({"email": ADMIN_EMAIL})
    password_hash = hash_password(ADMIN_PASSWORD)
    if not existing:
        await db.users.insert_one({"id": new_id(), "email": ADMIN_EMAIL, "password_hash": password_hash, "name": "Studio Admin", "role": "admin", "created_at": now_iso()})
        logger.info("Seeded administrator %s", ADMIN_EMAIL)
    elif not verify_password(ADMIN_PASSWORD, existing["password_hash"]):
        await db.users.update_one({"email": ADMIN_EMAIL}, {"$set": {"password_hash": password_hash}})


async def seed_content() -> None:
    if await db.settings.count_documents({}) == 0:
        await db.settings.insert_one({
            "id": new_id(), "business_name": "Studio Voxel", "tagline": "Spaces with a point of view.",
            "email": "hello@studiovoxel.co", "phone": "+44 20 7946 0182", "whatsapp": "+44 7700 900 101",
            "address": "18 Clerkenwell Road, London EC1M", "hours": "Mon–Fri · 09:00–18:00",
            "instagram": "https://instagram.com", "linkedin": "https://linkedin.com", "footer_note": "Architecture, interiors and objects for a more considered everyday.", "updated_at": now_iso()
        })
    if await db.page_content.count_documents({}) == 0:
        await db.page_content.insert_many([
            {"id": new_id(), "page": "home", "eyebrow": "Independent architecture studio · London / Lisbon", "headline": "We make room for better living.", "body": "Studio Voxel shapes calm, characterful places around the way people actually move, gather and rest.", "image_url": "https://images.unsplash.com/photo-1602128110234-2d11c0aaadfe?auto=format&fit=crop&w=1800&q=88", "updated_at": now_iso()},
            {"id": new_id(), "page": "about", "eyebrow": "The studio", "headline": "A quieter kind of ambition.", "body": "We are a small, curious team working across architecture, interiors and objects. Our practice begins with listening — to a site, a material, a daily ritual — and ends with work that feels inevitable.", "image_url": "https://images.pexels.com/photos/4977448/pexels-photo-4977448.jpeg?auto=compress&cs=tinysrgb&w=1400", "updated_at": now_iso()},
        ])
    if await db.services.count_documents({}) == 0:
        await db.services.insert_many([
            {"id": new_id(), "title": "Architecture", "short_description": "Buildings grounded in their context.", "description": "From first sketch to final handover, we create resilient, legible architecture that belongs to its place.", "image_url": "https://images.unsplash.com/photo-1600607687920-4e2a09cf159d?auto=format&fit=crop&w=1200&q=85", "icon": "01", "order": 1, "active": True, "created_at": now_iso()},
            {"id": new_id(), "title": "Interior worlds", "short_description": "Atmosphere, detail and everyday ease.", "description": "We tune light, texture, colour and proportion to make interiors that invite people to stay.", "image_url": "https://images.unsplash.com/photo-1600607688969-a5bfcd646154?auto=format&fit=crop&w=1200&q=85", "icon": "02", "order": 2, "active": True, "created_at": now_iso()},
            {"id": new_id(), "title": "Objects & direction", "short_description": "Small gestures with lasting presence.", "description": "Furniture, fittings and visual direction that bring a project’s ideas into focus.", "image_url": "https://images.unsplash.com/photo-1618220179428-22790b461013?auto=format&fit=crop&w=1200&q=85", "icon": "03", "order": 3, "active": True, "created_at": now_iso()},
        ])
    if await db.projects.count_documents({}) == 0:
        await db.projects.insert_many([
            {"id": new_id(), "slug": "house-for-a-long-summer", "title": "House for a long summer", "description": "A low-slung home that turns toward the garden, pairing robust materials with a soft, shifting light.", "image_url": "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=1600&q=88", "category": "Residential", "year": "2024", "location": "Algarve, PT", "featured": True, "order": 1, "active": True, "created_at": now_iso()},
            {"id": new_id(), "slug": "the-courtyard-office", "title": "The Courtyard Office", "description": "A former printworks becomes a generous workplace organised around a planted internal room.", "image_url": "https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1600&q=88", "category": "Workplace", "year": "2023", "location": "London, UK", "featured": True, "order": 2, "active": True, "created_at": now_iso()},
            {"id": new_id(), "slug": "shoreline-cabin", "title": "Shoreline Cabin", "description": "A compact retreat designed as a sequence of framed views, warm timber and wind-shaped landscape.", "image_url": "https://images.unsplash.com/photo-1510798831971-661eb04b3739?auto=format&fit=crop&w=1600&q=88", "category": "Hospitality", "year": "2022", "location": "Cornwall, UK", "featured": True, "order": 3, "active": True, "created_at": now_iso()},
        ])
    if await db.gallery.count_documents({}) == 0:
        gallery = [
            ("Travertine study", "Material", "https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?auto=format&fit=crop&w=1000&q=85"),
            ("Morning light", "Interiors", "https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=1000&q=85"),
            ("Concrete / olive", "Architecture", "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1000&q=85"),
            ("The long table", "Objects", "https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?auto=format&fit=crop&w=1000&q=85"),
            ("Threshold", "Architecture", "https://images.unsplash.com/photo-1600607687920-4e2a09cf159d?auto=format&fit=crop&w=1000&q=85"),
            ("Quiet corner", "Interiors", "https://images.unsplash.com/photo-1618220179428-22790b461013?auto=format&fit=crop&w=1000&q=85"),
        ]
        await db.gallery.insert_many([{ "id": new_id(), "title": title, "description": title, "image_url": image, "category": category, "alt_text": title, "order": index, "featured": index < 4, "active": True, "created_at": now_iso()} for index, (title, category, image) in enumerate(gallery, 1)])
    if await db.testimonials.count_documents({}) == 0:
        testimonials = [
            ("Ines Marques", "Founder", "Casa Marques", "Studio Voxel translated our loose brief into a home that feels inevitable. Every room settled into its own quiet rhythm.", "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=400&q=80"),
            ("David Okafor", "Head of Workplace", "Northshore Group", "We wanted a workplace that treated people like adults. The result is generous, calm and unmistakably ours.", "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=400&q=80"),
            ("Lena Fischer", "Creative director", "Fischer Studio", "A rare kind of collaboration — precise where it counts, playful where it should be.", "https://images.unsplash.com/photo-1573497019940-1c28c88b4f3e?auto=format&fit=crop&w=400&q=80"),
        ]
        await db.testimonials.insert_many([{ "id": new_id(), "title": name, "role": role, "company": company, "quote": quote, "image_url": image, "rating": 5, "featured": True, "order": idx, "active": True, "created_at": now_iso()} for idx, (name, role, company, quote, image) in enumerate(testimonials, 1)])
    if await db.team.count_documents({}) == 0:
        team = [
            ("Amelia Hart", "Principal architect", "Amelia leads the studio’s architectural practice. Twenty years of buildings that begin with the site and end with the way a door meets a wall.", "https://images.unsplash.com/photo-1544005316-04ce1f2f4a2b?auto=format&fit=crop&w=600&q=80"),
            ("Rafael Silva", "Interior lead", "Rafael shapes the interior worlds of the studio, working closely with clients on light, texture and everyday atmosphere.", "https://images.unsplash.com/photo-1521737604893-d14cc237f11d?auto=format&fit=crop&w=600&q=80"),
            ("Priya Shah", "Design manager", "Priya keeps every project on course, translating creative direction into buildable, believable detail.", "https://images.unsplash.com/photo-1554151228-14d9def656e4?auto=format&fit=crop&w=600&q=80"),
            ("Jonas Weber", "Objects & direction", "Jonas leads the studio’s furniture, fittings and visual direction — the small gestures with lasting presence.", "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=600&q=80"),
        ]
        await db.team.insert_many([{ "id": new_id(), "title": name, "role": role, "bio": bio, "image_url": image, "instagram": "", "linkedin": "", "order": idx, "active": True, "created_at": now_iso()} for idx, (name, role, bio, image) in enumerate(team, 1)])
    if await db.faqs.count_documents({}) == 0:
        faqs = [
            ("How do we start a project together?", "We begin with a short conversation to understand the site, the brief and the ambition. If it feels like a good fit on both sides, we prepare a proposal that outlines scope, phases and fee.", "Working together"),
            ("What size of projects do you take on?", "We work across scales — from a single considered room to full architectural commissions. We take on a small number of projects each year so every one gets the attention it deserves.", "Working together"),
            ("Do you work outside the UK?", "Yes. The studio has offices in London and Lisbon and has completed commissions across Europe. Travel and logistics are planned into every proposal.", "Working together"),
            ("What are your fees like?", "Fees are proposed per project after our first meeting. They typically reflect the scope, complexity and time required, and are shared as fixed stages so there are no surprises.", "Fees & timing"),
            ("How long does a typical project take?", "Small interiors move in months; new-build architecture unfolds over a year or more. We share a realistic timeline before you commit to anything.", "Fees & timing"),
            ("Can we manage construction ourselves?", "Absolutely. We are happy to hand over drawings and specifications to your builder, or to stay involved as your representative on site.", "During construction"),
        ]
        await db.faqs.insert_many([{ "id": new_id(), "title": question, "answer": answer, "category": category, "order": idx, "active": True, "created_at": now_iso()} for idx, (question, answer, category) in enumerate(faqs, 1)])
    if await db.blog.count_documents({}) == 0:
        posts = [
            ("Making room for the good stuff", "A short note on why the best rooms leave space for real life to happen — and how we design for it.", "There is a quiet discipline in leaving things out. In our studio we talk about designing for the ninety percent — the daily rhythm of a place — before we decorate the ten percent that gets photographed.\n\nWhen a room is planned around real routines, everything relaxes. Furniture stops fighting for attention. Light does most of the work. Materials age into the story instead of dating it.\n\nThat’s the version of ‘finished’ we care about.", "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1400&q=85", "Studio Voxel", "practice, philosophy", 1),
            ("Notes on a Portuguese summer", "Materials, weather and the slow pleasure of building on a coastal site in the Algarve.", "The Algarve teaches you to build in section. The sun asks for shade; the wind asks for shelter; the ground asks for weight.\n\nWe worked with a local mason to develop a lime render that could take the light without glare, and paired it with brushed oak that softens over years.\n\nThe result is a house that feels a little older than it is — and better for it.", "https://images.unsplash.com/photo-1600607687920-4e2a09cf159d?auto=format&fit=crop&w=1400&q=85", "Amelia Hart", "projects, materials", 2),
            ("On working with existing buildings", "Why we love a slightly awkward plan — and what it teaches every new design we start.", "Old buildings come with weight. Not just structural weight, but the weight of every choice that has already been made. That’s not a constraint; it’s a brief.\n\nWe start every retrofit by walking the space slowly, measuring, listening, and photographing details that might normally be dismissed. Nine times out of ten, the plan begins to tell us what it wants to become.", "https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1400&q=85", "Rafael Silva", "practice, refurbishment", 3),
        ]
        await db.blog.insert_many([{ "id": new_id(), "slug": slugify(title), "title": title, "excerpt": excerpt, "content": content, "image_url": image, "author": author, "tags": tags, "published": True, "order": order, "active": True, "created_at": now_iso()} for title, excerpt, content, image, author, tags, order in posts])


@app.on_event("startup")
async def startup() -> None:
    await db.users.create_index("email", unique=True)
    await db.projects.create_index("slug", unique=True)
    await db.blog.create_index("slug", unique=True)
    # Migrate legacy media URLs (pre-ingress-fix) to /api/uploads/...
    await db.media.update_many({"url": {"$regex": "^/uploads/"}}, [{"$set": {"url": {"$concat": ["/api", "$url"]}}}])
    await seed_admin()
    await seed_content()


@api_router.get("/")
async def root() -> Dict[str, str]:
    return {"message": "Studio Voxel CMS API", "status": "ready"}


@api_router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: JSONResponse) -> Dict[str, Any]:
    email = str(payload.email).lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    token = create_token(user["id"], email)
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    safe_user = clean_doc(user)
    return {"user": safe_user, "access_token": token}


@api_router.post("/auth/logout")
async def logout(request: Request, response: JSONResponse) -> Dict[str, Any]:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
            if payload.get("jti"):
                await db.revoked_tokens.update_one({"jti": payload["jti"]}, {"$set": {"jti": payload["jti"], "revoked_at": now_iso()}}, upsert=True)
        except jwt.InvalidTokenError:
            pass
    response.delete_cookie("access_token", path="/")
    return {"success": True, "message": "Signed out"}


@api_router.get("/auth/me", response_model=UserOut)
async def me(admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    return admin


@api_router.get("/site/home")
async def home_data() -> Dict[str, Any]:
    settings = clean_doc(await db.settings.find_one({}, {"_id": 0}))
    pages = await db.page_content.find({}, {"_id": 0}).to_list(20)
    return {"settings": settings, "pages": [clean_doc(page) for page in pages], "services": await sorted_items("services", True, 3), "projects": await db.projects.find({"active": True, "featured": True}, {"_id": 0}).sort("order", 1).to_list(6), "gallery": await db.gallery.find({"active": True, "featured": True}, {"_id": 0}).sort("order", 1).to_list(6), "testimonials": await db.testimonials.find({"active": True, "featured": True}, {"_id": 0}).sort("order", 1).to_list(6), "team": await db.team.find({"active": True}, {"_id": 0}).sort("order", 1).to_list(12)}


@api_router.get("/settings")
async def get_settings() -> Dict[str, Any]:
    return clean_doc(await db.settings.find_one({}, {"_id": 0})) or {}


@api_router.put("/settings")
async def update_settings(payload: SettingsPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = payload.model_dump()
    data["updated_at"] = now_iso()
    existing = await db.settings.find_one({}, {"_id": 0})
    if existing:
        await db.settings.update_one({"id": existing["id"]}, {"$set": data})
        data = {**existing, **data}
    else:
        data = {"id": new_id(), **data}
        await db.settings.insert_one(data)
    return clean_doc(data) or {}


@api_router.get("/content/{page}")
async def get_page_content(page: str) -> Dict[str, Any]:
    return clean_doc(await db.page_content.find_one({"page": page}, {"_id": 0})) or {}


@api_router.put("/content/{page}")
async def update_page_content(page: str, payload: PageContentPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = payload.model_dump()
    data["page"] = page
    data["updated_at"] = now_iso()
    existing = await db.page_content.find_one({"page": page}, {"_id": 0})
    if existing:
        await db.page_content.update_one({"id": existing["id"]}, {"$set": data})
        data = {**existing, **data}
    else:
        data = {"id": new_id(), **data}
        await db.page_content.insert_one(data)
    return clean_doc(data) or {}


@api_router.get("/services")
async def get_services() -> List[Dict[str, Any]]:
    return await sorted_items("services")


@api_router.post("/services")
async def create_service(payload: ServicePayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {"id": new_id(), **payload.model_dump(), "created_at": now_iso(), "updated_at": now_iso()}
    await db.services.insert_one(data)
    return clean_doc(data) or {}


@api_router.put("/services/{item_id}")
async def update_service(item_id: str, payload: ServicePayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {**payload.model_dump(), "updated_at": now_iso()}
    result = await db.services.find_one_and_update({"id": item_id}, {"$set": data}, projection={"_id": 0}, return_document=True)
    if not result:
        raise HTTPException(status_code=404, detail="Service not found")
    return clean_doc({**result, **data}) or {}


@api_router.delete("/services/{item_id}")
async def delete_service(item_id: str, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    result = await db.services.delete_one({"id": item_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"success": True, "message": "Service deleted"}


@api_router.get("/projects")
async def get_projects() -> List[Dict[str, Any]]:
    return await sorted_items("projects")


@api_router.get("/projects/{slug}")
async def get_project(slug: str) -> Dict[str, Any]:
    project = await db.projects.find_one({"slug": slug, "active": True}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return clean_doc(project) or {}


@api_router.get("/projects/{slug}/related")
async def get_project_related(slug: str) -> Dict[str, Any]:
    project = await db.projects.find_one({"slug": slug, "active": True}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    posts = await db.blog.find({"active": True, "published": True}, {"_id": 0}).sort([("order", 1), ("created_at", -1)]).to_list(3)
    testimonial = await db.testimonials.find_one({"active": True, "featured": True}, {"_id": 0}, sort=[("order", 1)])
    other_projects = await db.projects.find({"active": True, "slug": {"$ne": slug}}, {"_id": 0}).sort([("order", 1), ("created_at", -1)]).to_list(3)
    return {"posts": [clean_doc(post) for post in posts], "testimonial": clean_doc(testimonial), "projects": [clean_doc(proj) for proj in other_projects]}


@api_router.post("/projects")
async def create_project(payload: ProjectPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {"id": new_id(), "slug": slugify(payload.title), **payload.model_dump(), "created_at": now_iso(), "updated_at": now_iso()}
    await db.projects.insert_one(data)
    return clean_doc(data) or {}


@api_router.put("/projects/{item_id}")
async def update_project(item_id: str, payload: ProjectPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {**payload.model_dump(), "slug": slugify(payload.title), "updated_at": now_iso()}
    result = await db.projects.find_one_and_update({"id": item_id}, {"$set": data}, projection={"_id": 0}, return_document=True)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return clean_doc({**result, **data}) or {}


@api_router.delete("/projects/{item_id}")
async def delete_project(item_id: str, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    result = await db.projects.delete_one({"id": item_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"success": True, "message": "Project deleted"}


@api_router.get("/gallery")
async def get_gallery() -> List[Dict[str, Any]]:
    return await sorted_items("gallery")


@api_router.post("/gallery")
async def create_gallery(payload: GalleryPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {"id": new_id(), **payload.model_dump(), "created_at": now_iso(), "updated_at": now_iso()}
    await db.gallery.insert_one(data)
    return clean_doc(data) or {}


@api_router.put("/gallery/{item_id}")
async def update_gallery(item_id: str, payload: GalleryPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {**payload.model_dump(), "updated_at": now_iso()}
    result = await db.gallery.find_one_and_update({"id": item_id}, {"$set": data}, projection={"_id": 0}, return_document=True)
    if not result:
        raise HTTPException(status_code=404, detail="Gallery item not found")
    return clean_doc({**result, **data}) or {}


@api_router.delete("/gallery/{item_id}")
async def delete_gallery(item_id: str, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    result = await db.gallery.delete_one({"id": item_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Gallery item not found")
    return {"success": True, "message": "Gallery item deleted"}


@api_router.get("/media")
async def get_media(admin: Dict[str, Any] = Depends(current_admin)) -> List[Dict[str, Any]]:
    return [clean_doc(doc) for doc in await db.media.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)]


@api_router.post("/media/upload")
async def upload_media(files: List[UploadFile] = File(...), admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    if len(files) > 12:
        raise HTTPException(status_code=400, detail="Upload up to 12 images at a time")
    allowed = {"image/jpeg", "image/png", "image/webp"}
    created = []
    for upload in files:
        if upload.content_type not in allowed:
            raise HTTPException(status_code=400, detail="Only JPG, PNG and WEBP images are allowed")
        content = await upload.read()
        if len(content) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Each image must be under 8 MB")
        try:
            image = Image.open(BytesIO(content))
            image.verify()
            image = Image.open(BytesIO(content))
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid image") from exc
        if image.mode == "P":
            image = image.convert("RGBA")
        elif image.mode == "CMYK":
            image = image.convert("RGB")
        elif image.mode not in ("RGB", "RGBA", "L"):
            image = image.convert("RGB")
        max_dim = 1920
        if image.width > max_dim or image.height > max_dim:
            image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="WEBP", quality=85, method=6)
        webp_bytes = buffer.getvalue()
        filename = f"{uuid.uuid4().hex}.webp"
        (UPLOAD_DIR / filename).write_bytes(webp_bytes)
        original_name = upload.filename or filename
        base_name = original_name.rsplit(".", 1)[0][:120] + ".webp"
        item = {"id": new_id(), "filename": filename, "original_name": base_name, "content_type": "image/webp", "size": len(webp_bytes), "original_size": len(content), "width": image.width, "height": image.height, "url": f"/api/uploads/{filename}", "created_at": now_iso()}
        await db.media.insert_one(item)
        created.append(clean_doc(item))
    return {"success": True, "items": created}


@api_router.delete("/media/{item_id}")
async def delete_media(item_id: str, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    item = await db.media.find_one({"id": item_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found")
    file_path = UPLOAD_DIR / item["filename"]
    if file_path.exists():
        file_path.unlink()
    await db.media.delete_one({"id": item_id})
    return {"success": True, "message": "Media deleted"}


@api_router.get("/testimonials")
async def get_testimonials() -> List[Dict[str, Any]]:
    return await sorted_items("testimonials")


@api_router.post("/testimonials")
async def create_testimonial(payload: TestimonialPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {"id": new_id(), **payload.model_dump(), "created_at": now_iso(), "updated_at": now_iso()}
    await db.testimonials.insert_one(data)
    return clean_doc(data) or {}


@api_router.put("/testimonials/{item_id}")
async def update_testimonial(item_id: str, payload: TestimonialPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {**payload.model_dump(), "updated_at": now_iso()}
    result = await db.testimonials.find_one_and_update({"id": item_id}, {"$set": data}, projection={"_id": 0}, return_document=True)
    if not result:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    return clean_doc({**result, **data}) or {}


@api_router.delete("/testimonials/{item_id}")
async def delete_testimonial(item_id: str, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    result = await db.testimonials.delete_one({"id": item_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    return {"success": True, "message": "Testimonial deleted"}


@api_router.get("/team")
async def get_team() -> List[Dict[str, Any]]:
    return await sorted_items("team")


@api_router.post("/team")
async def create_team_member(payload: TeamPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {"id": new_id(), **payload.model_dump(), "created_at": now_iso(), "updated_at": now_iso()}
    await db.team.insert_one(data)
    return clean_doc(data) or {}


@api_router.put("/team/{item_id}")
async def update_team_member(item_id: str, payload: TeamPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {**payload.model_dump(), "updated_at": now_iso()}
    result = await db.team.find_one_and_update({"id": item_id}, {"$set": data}, projection={"_id": 0}, return_document=True)
    if not result:
        raise HTTPException(status_code=404, detail="Team member not found")
    return clean_doc({**result, **data}) or {}


@api_router.delete("/team/{item_id}")
async def delete_team_member(item_id: str, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    result = await db.team.delete_one({"id": item_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Team member not found")
    return {"success": True, "message": "Team member removed"}


@api_router.get("/faqs")
async def get_faqs() -> List[Dict[str, Any]]:
    return await sorted_items("faqs")


@api_router.post("/faqs")
async def create_faq(payload: FaqPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {"id": new_id(), **payload.model_dump(), "created_at": now_iso(), "updated_at": now_iso()}
    await db.faqs.insert_one(data)
    return clean_doc(data) or {}


@api_router.put("/faqs/{item_id}")
async def update_faq(item_id: str, payload: FaqPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {**payload.model_dump(), "updated_at": now_iso()}
    result = await db.faqs.find_one_and_update({"id": item_id}, {"$set": data}, projection={"_id": 0}, return_document=True)
    if not result:
        raise HTTPException(status_code=404, detail="FAQ not found")
    return clean_doc({**result, **data}) or {}


@api_router.delete("/faqs/{item_id}")
async def delete_faq(item_id: str, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    result = await db.faqs.delete_one({"id": item_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="FAQ not found")
    return {"success": True, "message": "FAQ deleted"}


@api_router.get("/blog")
async def get_blog(include_drafts: bool = False, admin: Optional[Dict[str, Any]] = Depends(optional_admin)) -> List[Dict[str, Any]]:
    query = {} if include_drafts and admin else {"active": True, "published": True}
    docs = await db.blog.find(query, {"_id": 0}).sort([("order", 1), ("created_at", -1)]).to_list(200)
    return [clean_doc(doc) for doc in docs if doc]


@api_router.get("/blog/{slug}")
async def get_blog_post(slug: str) -> Dict[str, Any]:
    post = await db.blog.find_one({"slug": slug, "active": True, "published": True}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return clean_doc(post) or {}


@api_router.post("/blog")
async def create_blog_post(payload: BlogPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {"id": new_id(), "slug": slugify(payload.title), **payload.model_dump(), "created_at": now_iso(), "updated_at": now_iso()}
    await db.blog.insert_one(data)
    return clean_doc(data) or {}


@api_router.put("/blog/{item_id}")
async def update_blog_post(item_id: str, payload: BlogPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {**payload.model_dump(), "slug": slugify(payload.title), "updated_at": now_iso()}
    result = await db.blog.find_one_and_update({"id": item_id}, {"$set": data}, projection={"_id": 0}, return_document=True)
    if not result:
        raise HTTPException(status_code=404, detail="Post not found")
    return clean_doc({**result, **data}) or {}


@api_router.delete("/blog/{item_id}")
async def delete_blog_post(item_id: str, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    result = await db.blog.delete_one({"id": item_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"success": True, "message": "Post deleted"}


class ContactStatusPayload(BaseModel):
    status: str = Field(pattern="^(new|read|archived)$")


@api_router.get("/dashboard")
async def dashboard(admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    stats = {collection: await db[collection].count_documents({}) for collection in ["services", "projects", "gallery", "media", "testimonials", "blog", "team", "faqs"]}
    stats["contact_submissions"] = await db.contact_submissions.count_documents({})
    stats["unread_contacts"] = await db.contact_submissions.count_documents({"status": "new"})
    recent = await db.projects.find({}, {"_id": 0, "id": 1, "title": 1, "image_url": 1, "created_at": 1}).sort("created_at", -1).to_list(4)
    return {"stats": stats, "recent_projects": [clean_doc(item) for item in recent]}


@api_router.get("/contact-submissions")
async def get_contact_submissions(admin: Dict[str, Any] = Depends(current_admin)) -> List[Dict[str, Any]]:
    docs = await db.contact_submissions.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [clean_doc(doc) for doc in docs if doc]


@api_router.put("/contact-submissions/{item_id}")
async def update_contact_submission(item_id: str, payload: ContactStatusPayload, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    data = {"status": payload.status, "updated_at": now_iso()}
    result = await db.contact_submissions.find_one_and_update({"id": item_id}, {"$set": data}, projection={"_id": 0}, return_document=True)
    if not result:
        raise HTTPException(status_code=404, detail="Submission not found")
    return clean_doc({**result, **data}) or {}


@api_router.delete("/contact-submissions/{item_id}")
async def delete_contact_submission(item_id: str, admin: Dict[str, Any] = Depends(current_admin)) -> Dict[str, Any]:
    result = await db.contact_submissions.delete_one({"id": item_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Submission not found")
    return {"success": True, "message": "Submission deleted"}


@api_router.post("/contact")
async def contact(payload: ContactPayload) -> Dict[str, Any]:
    submission = {"id": new_id(), **payload.model_dump(), "status": "new", "created_at": now_iso()}
    await db.contact_submissions.insert_one(submission)
    return {"success": True, "message": "Thank you — we will be in touch shortly."}


app.include_router(api_router)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"success": False, "detail": "Something went wrong. Please try again."})


@app.on_event("shutdown")
async def shutdown_db_client() -> None:
    client.close()