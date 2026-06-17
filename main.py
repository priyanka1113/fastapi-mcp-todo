"""
FastAPI Todo List Application with SQLite Database
A complete REST API for managing todo items with full CRUD operations.
Includes automatic API documentation (Swagger UI and ReDoc).
Uses SQLite for persistent local storage.
"""

import sqlite3
from pathlib import Path
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from fastapi_mcp import FastApiMCP

# ============================================================================
# Database Configuration
# ============================================================================

# Database file path - stored in application root
DATABASE_PATH = Path(__file__).parent / "todos.db"


def init_database() -> None:
    """
    Initialize SQLite database with todos table if it doesn't exist.
    Called on application startup.
    """
    connection = sqlite3.connect(DATABASE_PATH)
    cursor = connection.cursor()
    
    # Create todos table with primary key and default values
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            todo_id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            completed BOOLEAN DEFAULT 0
        )
    """)
    
    connection.commit()
    connection.close()


def get_db_connection() -> sqlite3.Connection:
    """
    Get a connection to the SQLite database.
    
    Returns:
        sqlite3.Connection: Active database connection.
    """
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row  # Enable column access by name
    return connection


# Initialize database on module load
init_database()


# ============================================================================
# FastAPI Application & Pydantic Models
# ============================================================================

# Initialize FastAPI app with metadata for automatic documentation
app = FastAPI(
    title="Todo List API",
    description="Complete CRUD API for managing todo items with SQLite database",
    version="1.0.0",
)


# Pydantic models for request/response validation with type hints
class TodoBase(BaseModel):
    """Base model for todo item with common fields."""
    content: str = Field(..., min_length=1, max_length=500, description="Todo content/description")
    completed: bool = Field(default=False, description="Completion status")


class TodoCreate(TodoBase):
    """Model for creating a new todo item."""
    pass


class TodoUpdate(BaseModel):
    """Model for updating a todo item (all fields optional)."""
    content: str | None = Field(None, min_length=1, max_length=500, description="Updated content")
    completed: bool | None = Field(None, description="Updated completion status")


class Todo(TodoBase):
    """Complete todo item model including ID (as returned from database)."""
    todo_id: int = Field(..., description="Unique todo identifier (primary key)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "todo_id": 1,
                "content": "Buy groceries",
                "completed": False,
            }
        }
    )


# ============================================================================
# Root & Health Check Endpoints
# ============================================================================

@app.get(
    "/",
    summary="Welcome endpoint",
    tags=["Root"],
)
async def root() -> dict[str, str]:
    """
    Root endpoint that returns a welcome message with API information.
    
    Returns:
        dict: Welcome message and links to API documentation.
    """
    return {
        "message": "Welcome to Todo List API",
        "status": "running",
        "docs": "Visit /docs for interactive API documentation (Swagger UI)",
        "redoc": "Visit /redoc for alternative documentation (ReDoc)",
    }


@app.get(
    "/health",
    summary="Health check",
    tags=["Health"],
)
async def health() -> dict[str, str]:
    """
    Health check endpoint to verify API and database are operational.
    
    Returns:
        dict: Health status and database info.
    """
    try:
        # Attempt to connect to database
        connection = get_db_connection()
        connection.execute("SELECT 1")
        connection.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database error: {str(e)}"
        )


# ============================================================================
# CRUD Operations - Todo Endpoints
# ============================================================================

@app.get(
    "/todos",
    response_model=list[Todo],
    summary="Get all todos",
    tags=["Todos"],operation_id="get_all_todos"
)
async def get_all_todos() -> list[Todo]:
    """
    Retrieve all todo items from the SQLite database.
    
    Returns:
        list[Todo]: List of all todo items ordered by creation (ID).
                   Returns empty list if no todos exist.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Query all todos ordered by ID
        cursor.execute("SELECT todo_id, content, completed FROM todos ORDER BY todo_id")
        rows = cursor.fetchall()
        connection.close()
        
        # Convert database rows to Todo models
        todos = [
            Todo(
                todo_id=row["todo_id"],
                content=row["content"],
                completed=bool(row["completed"])
            )
            for row in rows
        ]
        return todos
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )


@app.get(
    "/todos/{todo_id}",
    response_model=Todo,
    summary="Get a single todo by ID",
    tags=["Todos"],operation_id="get_todo_by_id"
)
async def get_todo(todo_id: int) -> Todo:
    """
    Retrieve a specific todo item by its ID from the database.
    
    Args:
        todo_id: The ID of the todo item to retrieve (path parameter).
    
    Returns:
        Todo: The requested todo item.
    
    Raises:
        HTTPException: 404 if todo item not found.
        HTTPException: 500 if database error occurs.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Query todo by ID
        cursor.execute(
            "SELECT todo_id, content, completed FROM todos WHERE todo_id = ?",
            (todo_id,)
        )
        row = cursor.fetchone()
        connection.close()
        
        # Return todo if found
        if row:
            return Todo(
                todo_id=row["todo_id"],
                content=row["content"],
                completed=bool(row["completed"])
            )
        
        # Raise 404 if not found
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Todo with id {todo_id} not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )


@app.post(
    "/todos",
    response_model=Todo,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new todo",
    tags=["Todos"],operation_id="create_todo"
)
async def create_todo(todo_create: TodoCreate) -> Todo:
    """
    Create a new todo item in the SQLite database.
    
    Args:
        todo_create: Request body with todo content and completion status.
    
    Returns:
        Todo: The newly created todo item with auto-generated ID.
    
    Raises:
        HTTPException: 500 if database error occurs.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Insert new todo into database
        cursor.execute(
            "INSERT INTO todos (content, completed) VALUES (?, ?)",
            (todo_create.content, todo_create.completed)
        )
        connection.commit()
        
        # Get the ID of inserted row
        new_id = cursor.lastrowid
        connection.close()
        
        # Return newly created todo
        return Todo(
            todo_id=new_id,
            content=todo_create.content,
            completed=todo_create.completed
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )


@app.put("/todos/{todo_id}",operation_id="update_todo",
    response_model=Todo,
    summary="Update an existing todo",
    tags=["Todos"],
)
async def update_todo(todo_id: int, todo_update: TodoUpdate) -> Todo:
    """
    Update an existing todo item (supports partial updates).
    Only provided fields are updated; omitted fields retain their values.
    
    Args:
        todo_id: The ID of the todo to update (path parameter).
        todo_update: Request body with fields to update.
    
    Returns:
        Todo: The updated todo item.
    
    Raises:
        HTTPException: 404 if todo item not found.
        HTTPException: 500 if database error occurs.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # First verify todo exists
        cursor.execute(
            "SELECT todo_id, content, completed FROM todos WHERE todo_id = ?",
            (todo_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            connection.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Todo with id {todo_id} not found"
            )
        
        # Prepare update values (use existing if not provided)
        updated_content = todo_update.content if todo_update.content is not None else row["content"]
        updated_completed = todo_update.completed if todo_update.completed is not None else row["completed"]
        
        # Update todo in database
        cursor.execute(
            "UPDATE todos SET content = ?, completed = ? WHERE todo_id = ?",
            (updated_content, updated_completed, todo_id)
        )
        connection.commit()
        connection.close()
        
        # Return updated todo
        return Todo(
            todo_id=todo_id,
            content=updated_content,
            completed=bool(updated_completed)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )


@app.delete("/todos/{todo_id}", operation_id="delete_todo",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a todo",
    tags=["Todos"],
)
async def delete_todo(todo_id: int) -> None:
    """
    Delete a todo item from the database.
    
    Args:
        todo_id: The ID of the todo to delete (path parameter).
    
    Raises:
        HTTPException: 404 if todo item not found.
        HTTPException: 500 if database error occurs.
    """
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Check if todo exists before deleting
        cursor.execute("SELECT todo_id FROM todos WHERE todo_id = ?", (todo_id,))
        if not cursor.fetchone():
            connection.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Todo with id {todo_id} not found"
            )
        
        # Delete todo from database
        cursor.execute("DELETE FROM todos WHERE todo_id = ?", (todo_id,))
        connection.commit()
        connection.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )


# ============================================================================
# MCP Server
# ============================================================================

mcp = FastApiMCP(
    app,
    include_operations=[
        "get_all_todos",
        "get_todo_by_id",
        "create_todo",
        "update_todo",
        "delete_todo",
    ],
)
mcp.mount_http()


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )