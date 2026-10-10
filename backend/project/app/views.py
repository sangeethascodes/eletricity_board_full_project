from calendar import month
from typing import Any

from django.shortcuts import render
from django.http import HttpResponse
import pandas as pd
from .forms import CsvUploadForm
from .models import Applicant, Connection, Status
from datetime import datetime
from pathlib import Path
from django.views.generic import ListView
from django.http import JsonResponse
import json
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.contrib.auth import authenticate,login,logout

# Create your views here.

def parse_upload_date(value, column_name):
    if pd.isna(value):
        return None
    parsed_date = pd.to_datetime(value, dayfirst=True, errors='coerce')
    if pd.isna(parsed_date):
        raise ValueError(f'Invalid date in {column_name}: {value}')
    return parsed_date.date()

def index(request):
    return render(request, "index.html")

def login(request):
    return render(request, "login.html")

@csrf_exempt
def uploaddata(request):
    if request.method != 'POST':
        return render(request, 'upload.html', {'form': CsvUploadForm()})

    form = CsvUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, 'upload.html', {'form': form})

    try:
        uploaded_file = form.cleaned_data['csv_file']
        file_signature = uploaded_file.read(4)
        uploaded_file.seek(0)
        if Path(uploaded_file.name).suffix.lower() == '.csv' and file_signature != b'PK\x03\x04':
            df = pd.read_csv(uploaded_file, encoding='latin-1')
        else:
            df = pd.read_excel(uploaded_file)
        df.columns = df.columns.astype(str).str.strip()
        if 'Reviewer_Id' not in df.columns and 'Reviewer_ID' in df.columns:
            df = df.rename(columns={'Reviewer_ID': 'Reviewer_Id'})
        if 'user_id' not in df.columns and 'ID' in df.columns:
            df = df.rename(columns={'ID': 'user_id'})
        if 'user_id' not in df.columns and 'id' in df.columns:
            df = df.rename(columns={'id': 'user_id'})
        required_columns = {
            'user_id', 'Applicant_Name', 'Gender', 'District', 'applicant_state', 'Pincode',
            'Ownership', 'GovtID_Type', 'ID_Number', 'Category', 'Status',
            'Date_of_Application', 'Date_of_Approval', 'Modified_Date',
            'Load_Applied', 'Reviewer_Id', 'Reviewer_Name', 'Reviewer_Comments',
        }
        missing_columns = required_columns.difference(df.columns)
        if missing_columns:
            raise ValueError(
                f'Missing columns: {", ".join(sorted(missing_columns))}'
            )
                
        for index, row in df.iterrows():
            #create or update dont duplicate
            applicant, created = Applicant.objects.get_or_create(
            user_id=row.get('user_id', row.get('ID', row.get('id'))),
            Applicant_Name=row['Applicant_Name'],
            Gender=row['Gender'],
            District=row['District'],
            applicant_state=row['applicant_state'],
            Pincode=row['Pincode'],
            Ownership=row['Ownership'],
            GovtID_Type=row['GovtID_Type'],
            ID_Number=row['ID_Number'],
            Category=row['Category'],
            )
            
            
            #create or get the status object
            status, created=Status.objects.get_or_create(Status_Name=row['Status'])
            Date_of_Application = parse_upload_date(
                row['Date_of_Application'], 'Date_of_Application'
            )
            Date_of_Approval = parse_upload_date(
                row['Date_of_Approval'], 'Date_of_Approval'
            )
            Modified_Date = parse_upload_date(row['Modified_Date'], 'Modified_Date')
            
            Connection.objects.get_or_create(
                
                Applicant=applicant,
                Load_Applied=row['Load_Applied'],
                Date_of_Application=Date_of_Application,
                Date_of_Approval=Date_of_Approval,
                Modified_Date=Modified_Date,
                Status=status,
                Reviewer_ID=row['Reviewer_Id'],
                Reviewer_Name=row['Reviewer_Name'],
                Reviewer_Comments=row['Reviewer_Comments'],
            )
    except Exception as e:
        return HttpResponse(f'File is not uploaded or updated: {e}', status=400)
                        
    return HttpResponse('File is uploaded or updated')


class ConnectionListView(ListView):
    model=Connection
    context_object_name='connection'
    paginate_by=5
    
    def get_queryset(self):
       queryset = super().get_queryset()
        #Retrieve search query from the request
       search_query = self.request.GET.get('search')
        #Retireve date range parameters
       start_date_param = self.request.GET.get('start_date')
       end_date_param = self.request.GET.get('end_date')
        #Parse date range parameters if provided
       start_date = parse_date(start_date_param) if start_date_param else None
       end_date = parse_date(end_date_param) if end_date_param else None
    
    # Filter connections queryset based on the search query
       if search_query:
           queryset = queryset.filter(Applicant__user_id__icontains=search_query)
           
           # Filter connections queryset based on the date range
       if start_date and end_date:
           queryset = queryset.filter(Date_of_Application__gte = start_date, Date_of_Application__lte = end_date)
           
           
       return queryset
       
       
    
    def get_context_data(self, **kwargs):
        context=super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search')
        return context
    
    def render_to_response(self, context, **response_kwargs):
  
        serialized_data=[
            {
                'id': conn.Applicant.id,
                'user_id': conn.Applicant.user_id or conn.id,
                'Load_Applied':conn.Load_Applied,
                'Date_of_Application':conn.Date_of_Application,
                'Status':conn.Status.Status_Name,
                'Applicant':{
                    'id': conn.Applicant.id,
                    'user_id': conn.Applicant.user_id or conn.id,
                    'Applicant_Name': conn.Applicant.Applicant_Name,
                    'Gender': conn.Applicant.Gender,
                    'District': conn.Applicant.District,
                    'applicant_state': conn.Applicant.applicant_state,
                    'Pincode': conn.Applicant.Pincode,
                    'Ownership': conn.Applicant.Ownership,
                    'GovtID_Type': conn.Applicant.GovtID_Type,
                    'ID_Number': conn.Applicant.ID_Number,
                    'Category': conn.Applicant.Category,
                },
                'Reviewer_ID': conn.Reviewer_ID,
                'Reviewer_Name': conn.Reviewer_Name,
                'Reviewer_Comments': conn.Reviewer_Comments,
            }
            
            for conn in context['connection']
        ]
        
        
        response_data={
            'data':serialized_data,
            'search_query':context['search_query'],
            'total_pages':context['paginator'].num_pages,
            'current_page':context['page_obj'].number
        }
        
        return JsonResponse(response_data)
        
@csrf_exempt
def update_applicant(request,id):
    if request.method == 'GET':
        try:
            applicant = Applicant.objects.get(pk=id)
            connection = Connection.objects.get(Applicant = applicant)
            applicant_data = {
                "Applicant_Name": applicant.Applicant_Name,
                "Gender": applicant.Gender,
                "District": applicant.District,
                "applicant_state": applicant.applicant_state,
                "Pincode": applicant.Pincode,
                "Ownership": applicant.Ownership,
                "GovtID_Type":applicant.GovtID_Type,
                "ID_Number": applicant.ID_Number,
                "Category": applicant.Category
            }
            connection_data = {
                "Load_Applied": connection.Load_Applied,
                "Date_of_Application": connection.Date_of_Application,
                "Date_of_Approval": connection.Date_of_Approval,
                "Modified_Date": connection.Modified_Date,
                "Status": connection.Status.Status_Name,
                "Reviewer_ID": connection.Reviewer_ID,
                "Reviewer_Name": connection.Reviewer_Name,
                "Reviewer_Comments": connection.Reviewer_Comments
            }
            return JsonResponse({'applicant': applicant_data, 'connection': connection_data})
        except Applicant.DoesNotExist:
            return JsonResponse({'error':"Applicant not found"},status=404)
        except Connection.DoesNotExist:
            return JsonResponse({'error':"Connection not found"},status=404)
        
    elif request.method=='POST':
        try:
            applicant = Applicant.objects.get(pk=id)
            connection = Connection.objects.get(Applicant = applicant)
            data = json.loads(request.body)
            status_name = data.get('connection', {}).get('Status')
            status_instance = Status.objects.filter(Status_Name=status_name).first()
            if status_instance:
                applicant_data = data.get('applicant', {})
                for key, value in applicant_data.items():
                    setattr(applicant, key, value)
                applicant.save()
                
                connection_data = data.get('connection', {})
                for key, value in connection_data.items():
                    if key != 'Status':
                        setattr(connection, key, value)
                
                connection.Status = status_instance
                connection.save()
                
                return JsonResponse({'success': 'Applicant details updated successfully'})
            else:
                return JsonResponse({'error': 'Invalid status value'}, status=404)
        except Applicant.DoesNotExist:
            return JsonResponse({'error': 'Applicant not found'}, status=404)
        except Connection.DoesNotExist:
            return JsonResponse({'error': 'Connection not found'}, status=404)
        
def connectionvisualization(request):
    connection_requests = (
        Connection.objects.annotate(month=TruncMonth('Date_of_Application'))
        .values('month')
        .annotate(total_requests=Count('id'))
        .order_by('month')
    )

    labels = [entry['month'].strftime('%B %Y') for entry in connection_requests]
    total_requests = [entry['total_requests'] for entry in connection_requests]

    return JsonResponse({'labels': labels, 'total_requests': total_requests})

def connectionrequestdata(request):
    selected_status=request.GET.get('status')
    if selected_status:
        filtered_connections=Connection.objects.filter(Status__Status_Name=selected_status)
    else:
        filtered_connections=Connection.objects.all()
    data=filtered_connections.annotate(month=TruncMonth('Date_of_Application')).values('month').annotate(total_requests=Count('id')).order_by('month')
    
    labels=[entry ['month'].strftime('%B %Y') for entry in data]
    total_requests = [entry['total_requests'] for entry in data]
    
    return JsonResponse({'labels':labels,'total_requests': total_requests})


@csrf_exempt
def handlelogin(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        
        if username and password:
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return JsonResponse({'user': user.username}, status=200)
            else:
                return JsonResponse({'error': 'Invalid credentials'}, status=400)
        else:
            return JsonResponse({'error': 'Username and password are required'}, status=400)
    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)