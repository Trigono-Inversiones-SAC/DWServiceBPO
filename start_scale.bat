@echo off
call D:\BPO\BPO-ABack\env\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000