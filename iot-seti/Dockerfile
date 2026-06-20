# Folosim o versiune oficială și stabilă de Python
FROM python:3.10-slim

# Setăm folderul de lucru în interiorul containerului
WORKDIR /app

# Copiem doar lista de librării și le instalăm
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiem restul proiectului tău în container
COPY . .