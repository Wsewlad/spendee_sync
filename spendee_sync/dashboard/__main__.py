"""Entry point: python -m spendee_sync.dashboard"""
import uvicorn


def main():
    uvicorn.run(
        "spendee_sync.dashboard.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
