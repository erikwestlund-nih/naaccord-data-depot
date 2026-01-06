from django_components import register

from depot.components.form_page_component import FormPageComponent
from depot.data.upload_prechecker import Auditor
from depot.models import DataFileType
import tempfile
import os
import uuid


@register("pages.audit")
class AuditPage(FormPageComponent):
    user = None
    title = "Audit A Data File"
    validators = {
        "data_file_type": "required",
        "data_content": "required_when:upload_method=paste|You must provided CSV data when Paste CSV File is selected.",
        "uploaded_csv_file": "required_when:upload_method=upload|You must upload a file when CSV File Upload is selected.",
        "upload_method": "required",
    }
    data_file_type_options = []
    props = ["data_file_type", "data_content", "upload_method", "audit_report"]
    upload_props = ["uploaded_csv_file"]

    upload_options = [
        {"value": "upload", "label": "CSV File Upload"},
        {"value": "paste", "label": "Paste CSV File"},
    ]

    # for testing
    init_data = {
        # "data_file_type": "patient",
        # "data_file_type": "diagnosis",
        "data_file_type": "laboratory",
        # "data_file_type": "medication",
        # "data_file_type": "mortality",
        # "data_file_type": "geography",
        # "data_file_type": "encounter",
        # "data_file_type": "insurance",
        # "data_file_type": "hospitalization",
        # "data_file_type": "substance_survey",
        # "data_file_type": "procedure",
        # "data_file_type": "discharge_dx",
        # "data_file_type": "risk_factor",
        # "data_file_type": "census",
        # "upload_method": "upload",
        "upload_method": "paste",
        # patient
        # "data_content": "cohortPatientId,birthSex,presentSex,birthYear,race,hispanic,enrollDate,lastActivityDate,deathDate,deathDateSource,subSiteID,hivNegative,BirthCountry,transgendered,LastNDIDate\nea442e3a-5e7f-4b29-9c49-05ec294c6a39,Female,Male,1963,Native American,1,1999-02-26,2021-06-15,2021-02-26,SSDI,47,S,Paraguay,Yes,2022-10-16\nbf4bf951-f291-4102-8ab1-8c6992db19de,Female,Intersexed,2000,Asian,1,2011-07-21,2023-12-14,2021-04-08,Clinic reported,31,S,US,No,2024-07-29\n0c041937-9eae-4af3-8d74-70c110a128b4,Male,Intersexed,1902,Multiracial,0,2015-03-24,2022-05-17,,Clinic reported,63,Y,Aruba,No,2020-10-09\n88e700d6-7f55-46fd-adf9-19b8f87896c2,Male,Male,1960,Other,0,2012-04-15,2022-12-09,,SSDI,64,Y,US,Yes,2023-09-14\nec86f945-fee2-4201-a88a-966459b59af7,Intersexed,Female,1934,Unknown,0,2014-10-10,2020-10-11,2020-04-02,Clinic reported,85,Y,US,No,2016-06-20\n6071ffe4-0dd7-408f-821f-a96a7fd9c0f8,Female,Intersexed,1949,Unknown,1,2005-09-27,2021-07-21,,Clinic reported,71,Y,Greenland,No,2015-08-27\n7c8059f0-de65-4093-90fd-d985c7809b5e,Male,Male,2006,Pacific Islander,0,2009-11-12,2021-04-04,,Clinic reported,59,Y,Niger,Yes,2019-01-14\n681a8a7f-0dd7-421d-94e5-6c55f99df2b6,Male,Intersexed,1957,Other,0,2002-06-24,2021-10-12,,Clinic reported,17,Y,US,No,2022-01-22\n489f508b-2bc2-4b36-83bf-aa5acc70fcc7,Intersexed,Female,1904,Unknown,1,2004-07-19,2022-10-06,2021-07-04,Clinic reported,79,Y,US,Yes,2016-03-18\ne862f5b0-b57e-44f5-8b51-98fbe790f4d0,Male,Female,1965,Black,1,2006-12-28,2024-06-04,,SSDI,97,S,Gibraltar,No,2017-04-27\n",
        # diagnosis
        # "data_content": "cohortPatientId,diagnosis,diagnosisDate,source\n05fb98aa-fcc2-4802-aa85-df3e67baa3e4,Anxiety,02-14-2022,D2\n576d5d78-3671-4f6a-aae6-0de22e818a90,J18.9,2004-09-08,D2\n10dd03f4-b8eb-4dc2-b18e-fcbe0b3d1a59,Hypertension,2011-10-30,D5\n70345cbc-32e6-48a3-b242-7c3f4fab18e6,B20,2020-11-26,D3\n0aacdf32-7c72-493d-89f2-078f0e966d08,Hypertension,2023-05-07,D5\n0e89b648-0895-4d22-a5c9-bc7de7a89a90,I21.01,1998-08-25,D4\n458cdbd3-afb2-4de4-b05f-4a9f8bc8705b,250.00,2002-10-02,D3\n5f1ac08a-5427-430f-8679-b5798288ab8f,J18.9,2000-03-06,D2\nce9d93b9-eb96-4b8b-9b3e-670678aa97c3,250.00,2015-06-10,D3\nda284291-a12f-477a-90b7-2d5d4eea631c,250.00,2001-08-13,D3\n",
        # laboratory
        "data_content": 'cohortPatientId,testName,result,units,normalMin,normalMax,interpretation,resultDate,source\n814cb30d-e21e-4e66-a5d4-d5de86d5363b,Abs CD4,BLQ,U/L,3.73,48.0,ALQ,2020-10-05,L3\n02c20da0-5814-47c9-bf51-4a57b673e0da,Hemoglobin,Low,g/dL,2.25,68.29,Low,2000-03-23,L4\n19ea4b5b-3479-4591-89d6-16f0c1613e55,Hemoglobin,">75,000",U/L,3.61,11.46,BLQ,2001-12-15,L5\n1c437cdc-4a99-4288-ba4d-e87567b78922,Cholesterol,11.9,mMol/L,0.75,48.31,ALQ,2015-09-18,L3\nbb099b7d-c7cb-442b-b47d-6167b347053f,Cholesterol,Low,copies/mL,7.46,67.37,BLQ,2012-03-05,L2\n7995a5fa-f25b-4d3d-b11d-8b2fbe244cc1,Albumin,<50,THOU/uL,2.4,10.23,Normal,2021-12-20,L1\n51229237-8051-444e-aeff-771ddff372cd,Hemoglobin,Low,mMol/L,,17.22,nadir,2006-04-11,L2\n4c7f3e7e-cc8e-451f-b1c4-1ad40d706dfe,ALT,BLQ,THOU/uL,1.38,97.39,nadir,2020-12-07,L3\nc7810d72-43ef-4430-8d73-fce7a955218c,Triglycerides,19.0,g/dL,,65.88,,2017-04-29,L1\n7e092e39-98c5-4984-af15-d7ad4f43e010,Hemoglobin,<50,THOU/uL,2.61,85.83,Abnormal,2011-06-04,L4\n',
        # medication
        # "data_content": "cohortPatientId,medicationName,startDate,stopDate,form,strength,units,route,sig,source\n3ec64deb-6d20-442a-a0d4-dbc0393c52b6,Indinavir,1996-02-20,2030-08-13,Patch,800,mg/ml,,,M2\neeb24fe9-fabe-468c-ab04-451b9c759015,Lamivudine,,,,,,,Take 1 pill daily,M2\n95883a92-193d-4953-9c1b-76ff24c51e02,Efavirenz,2005-01-24,,,300,mcg,,,M3\n6f75a528-3b51-440c-b771-855e9af42880,Stavudine,2001-07-08,2033-05-24,,600,,IV,,M4\nb73456e8-f2a7-47c6-b58b-eb2f12071f10,Testosterone,2012-06-20,,Liquid,300,cc,,,M3\n683686d9-1d90-4dd3-93a9-349ca401fe41,Zidovudine,2003-09-17,2034-03-01,Liquid,,cc,by mouth,2BID,M5\nb0b6845e-07e3-40be-8f06-5428666905db,Lamivudine,2003-11-23,2025-12-22,,150,,,Q8H,M1\na3b026f6-e24c-463a-959a-6977d5d64e25,Stavudine,,2026-08-11,,,,,,M2\n7c42f17b-6f00-4bf0-9259-fea1a92ffdc0,Indinavir,2021-07-18,2029-08-23,,,,,1BID,M3\n8f48b853-1991-40e4-b4d7-bf3257e6d0b9,Indinavir,2004-09-18,2030-04-06,Patch,,cc,,1BID,M3\n",
        # mortality
        # "data_content": "cohortPatientId,cause,type,source\naf0026ff-9025-4f49-8803-fcfbd7aff0f1,Cardiopulmonary arrest,4,3\nc09b1d28-9e99-412a-b514-71116c268e6b,Bacterial sepsis,3,3\n1289f9a2-4586-4a71-882f-bb56d86a7ee0,Lung cancer,5,6\n8bfd29a5-195b-442c-a1bc-9f873c53ad70,Upper GI Bleed,2,1\n374fdba0-dca1-4eed-b67d-cd11ecd3dc87,Upper GI Bleed,3,9\n657b41ea-2a0c-4017-afcd-f53216103461,HIV Infection,5,1\nd2ae6ed7-e15c-4c23-9b88-e50c7bcdd764,Respiratory arrest,5,3\n0bfaa3b6-f73c-475f-8ebd-d5c689b95628,Cardiopulmonary arrest,1,1\nebea5f45-3627-4559-99c4-8c3092b4b997,PCP,2,3\nfbc33fa3-cc29-4fb8-bb15-acd7b305ac27,Pneumonia,1,1\n",
        # geography
        # "data_content": "cohortPatientId,stateProv,postCode,resDate,stateProvApprox\n9bf1e29a-566a-4cd9-91ce-3d32459af80d,NY,ZZZ,2022-05-26,False\n5aaae852-834c-4a39-9dc6-0be20224a9a8,WA,13006,1996-01-07,False\n66569b67-4483-4aba-abe8-927661c7527e,FL,12885,2019-12-31,False\n12af48dd-84b9-463c-a570-e5c20da8126f,TX,ZZZ,2016-04-24,True\n80f1a717-32bd-4848-b135-42ebb4dd14f7,FL,49822,2003-12-07,False\n50b709a8-c3a8-45d0-8db2-d1be4fd58db0,QC,32521,2010-04-10,False\n6ad27fa2-520d-403f-a6cd-bc774d33ecb5,ON,18765,2018-09-30,False\n52dfc492-e874-4fc5-9704-b0bce82fa190,CA,54826,2010-06-25,False\nb065bf72-4bb8-4fe4-abc3-c91ae987cebc,AB,ZZZ,2004-11-08,True\na524e163-ab48-4249-94be-5a2d7519c8d6,QC,ZZZ,2002-01-31,False\n"
        # encounter
        # "data_content": "cohortPatientId,encounterDate,encounterType,encounterInsType1,encounterInsType2,encounterInsType3,encounterInsType4,encounterInsType5\nc1f05480-a6a9-418a-bc28-fd6c8e08da83,2020-01-10,Interview visit – unspecified,3,,,,\n1da68345-a0b0-4b14-957f-ba001baf0e3d,2008-08-17,Telemedicine – Video,4,,,,\n5971c138-3ab6-45dc-bbf9-2924386afb4d,2019-10-23,HIV Primary Care,2,4,,,\n5e5f9469-71c6-4ad6-9ac6-8624cc90c1cc,2009-01-18,Telemedicine – Unspecified,5,,,,\n69a27460-f941-485a-9358-8bef1492f253,2018-04-04,Telemedicine – Unspecified,2,,9,,\n2739c199-29e3-4ca9-bae7-23477ee36b2a,2021-05-10,Interview visit – in-person,1,,,,\n0e1a530a-cf4b-4d2c-8b69-d38df1a13d28,2012-04-23,Interview visit – not in-person,6,,,,\ncd410382-89d0-455d-a451-7defc288aec1,2012-03-24,HIV Primary Care,8,,,,\n218c960b-b3b3-462f-b011-adeb5f4dbbf8,2017-09-03,Telemedicine – Video,8,2,,1,\n08464057-3258-4aaf-b718-4a4bde1e6b3f,2022-03-22,Interview visit – in-person,8,,,,\n"
        # insurance
        # "data_content": "cohortPatientId,insurance,insuranceStartDate,insuranceStopDate\n09d6d754-18e6-4f89-94e7-f1a1d65587e0,6,2004-02-23,2023-05-29\n80f11eb7-f2d2-42a8-84c5-a1c455777ebb,2,2024-09-27,2011-05-01\n5b5d85f1-f5ba-4ed1-af19-c1adabfb7a5b,7,2024-02-20,\n5eea4f88-acbc-4f04-9dce-a32a9a090136,7,1997-07-21,2019-04-01\n27e7c5b9-5b3a-4b51-bc19-2a863e922b38,7,2005-03-21,2020-05-13\n1fd285e6-3f2b-4729-8434-38f60467c221,4,2004-01-19,2008-07-20\na955b9d8-0fa9-45ee-8718-79dbe426193b,2,2018-02-13,2012-12-30\n2973112b-cffd-4400-a61e-6e9bc9651e49,99,2024-11-28,2007-11-29\nc65bcf33-69be-412f-8872-0673b8f300be,5,2008-04-05,2022-06-20\n1bb5e15d-f278-4136-8d95-d9e8152994e3,1,2008-07-09,\n",
        # hospitalization
        # "data_content": "cohortPatientId,encounterID,admitDate,dischargeDate\n117ec7c2-f08b-49a0-85f3-50269980882c,f6625bbc-8529-484f-9805-b8d60620fbf6,2007-12-13,2008-04-25\nc0449a00-390b-4483-a982-17e5379d6f65,41e6ec15-d818-423f-99e5-d16521884381,2018-03-21,1997-02-06\n38854527-7a48-4254-8502-521929c4a686,68f36bed-0207-4036-9164-66d125800334,1999-08-06,2005-05-03\nb41f39df-4a63-43cc-87a2-aa3eb0dfa2b6,24498c24-bdd3-4fff-9d97-e3c8b07931b6,2014-02-13,2023-12-01\n7be98b1f-a405-4b6f-9bdf-ffdf106cc040,4a13afcd-7e9e-4f59-87ba-b7f9eddc095d,2008-10-31,2004-03-21\nbcca653c-ebf6-4260-ade0-25ab3d95c79c,b912662e-e99e-4452-b462-03ec74decca6,1998-04-01,2017-02-19\n1c9fb458-2384-4b47-89a6-7e00ff9564ef,5839e4b5-e24e-456b-ac88-e169899b1302,2020-03-05,2009-10-16\nc874782b-da17-4a83-9f89-c87b76a56815,019abb2e-cf7a-4f6f-95ce-a41b1efb2c46,1998-12-04,2012-05-29\n635829a1-d9ca-48bc-b573-4af4b28b8133,22d2a8a3-beff-42f2-9255-1c038d5dbd03,2008-10-20,2004-02-22\ncc287389-c21a-4518-bf51-e77eb2bcec5f,e5eed314-72dd-4611-abb5-bc098bdffab5,2012-10-22,1999-12-05\n"
        # substance_survey
        # "data_content": "cohortPatientId,question,response,responseDate,questionLabel,responseLabel\neaf1bf58-ad20-4d02-9dc7-901c81bdd183,drinksday,No,2010-06-29,How often do you consume alcohol?,Never\n1aa3d1aa-56bb-4651-ab5a-d3757f74da0f,drinksday,Yes,2023-01-31,How many drinks per day?,Light use\n39c857ad-57ba-4b51-bab7-61284e66b3e4,caffeine,Occasionally,2014-11-22,Have you used illicit drugs?,Occasionally\n5cff9f15-6769-451b-842f-a789354c9e4c,smoke1,Daily,2021-10-04,Have you ever smoked?,Heavy use\n4ad317c1-45f7-4e62-88ef-4dced9e6044f,drinksday,4-6,2019-02-04,Have you ever smoked?,Occasionally\nf6e8364d-c9b3-411b-850e-bbcf06f7f6ef,drinksday,Never,2013-04-15,How much caffeine do you consume daily?,Heavy use\nea4ed1ec-b00d-4941-87bc-84d36bf1a973,caffeine,Yes,2006-05-31,Have you used illicit drugs?,Heavy use\ne489e042-f9b5-4dc0-ba40-f75b1f0b323f,drinksday,Occasionally,2019-05-24,How often do you consume alcohol?,Light use\neefffa2f-68e8-4045-b693-d03446c474ce,druguse,Daily,2019-05-13,How often do you consume alcohol?,Light use\nfe9c7e81-2519-41fa-9cba-77bf20192e1c,alcoholfreq,4-6,2017-12-05,How many drinks per day?,Never\n"
        # procedure
        # "data_content": "cohortPatientId,siteProcedure,procedureDate,procedureResult,source\ne5c93590-6c25-431c-b65a-0e816dccf00a,G0101,1995-09-23,3.9 KPa,P2\n18e80d06-92d3-4a67-b891-64c653df7412,G0101,2023-04-10,Abnormal,P3\n6b502cef-8a07-4bd6-bd62-dd8e94934c05,99213,2002-09-20,3.9 KPa,P3\nc0aa4084-5470-4d86-8f79-091b8d18cf83,99213,2016-10-03,3.9,P2\nc53acee4-11b9-47c1-a9c3-8b4d12fab445,G0101,2022-10-10,Abnormal,P1\n5ff37a1b-b1cc-475b-8032-a937db142f59,93000,2012-11-17,Abnormal,P1\n29d8d83b-5d06-4d38-b380-dec249a6ecb4,A0427,1999-04-08,3.9 KPa,P2\n22eedb11-8fec-4cb8-8ab1-560963168243,99213,1999-05-06,Normal,P3\n6b9cffd5-d128-4512-8ac1-eb46372faac3,A0427,2015-10-10,Normal,P4\n9a7a7216-af50-4a7c-a998-6693ae7b8ac5,99213,2012-06-13,No significant findings,P4\n"
        # discharge_dx
        # "data_content": "cohortPatientId,dischargeDx,dischargeDxDate,ranking,source,encounterID\n9c0161e5-e078-4a18-b6fa-d1b7b5abb66b,070.70,2007-04-28,4,Data collected at NA-ACCORD site,c5e508a8-6eec-4967-bc59-620c5aacfc93\nacc66bad-9d8d-4393-8972-8f29e111a3e3,481,2007-07-22,5,Data collected at NA-ACCORD site,f7da2d38-21f9-4e8d-8337-af987af49965\ned1e3e6d-c91b-48a8-916d-cac913ab3e85,481,2003-04-25,25,Data collected at NA-ACCORD site,96221318-aefc-4f19-81a9-f25f4795c2bc\nb60af328-00ae-47ca-868e-06c54ba71076,V46.2,2018-12-23,1,Data collected at NA-ACCORD site,fa5aeb2b-d3e8-4e12-9f64-b6052c38168c\ne3f63be9-cd2a-4838-9c0e-ce87d749cc36,518.83,2005-07-19,20,Data collected at NA-ACCORD site,1b4c63bb-925c-4a51-a962-ad074212798b\nb74db4a7-10a6-4e19-939a-613e066e6e8a,070.70,2004-08-22,27,Data collected at NA-ACCORD site,ae79e8db-2e31-4e8b-b277-ab1b8fed820d\nfd5ba59b-b201-480a-974b-8329ddbe996a,070.70,2023-06-14,14,Data collected at NA-ACCORD site,c973ac0a-35a9-44f4-a23c-a918d4b85f5c\n111d7710-bf31-469d-8ae1-d07305d74f9f,481,2012-03-01,12,Data collected at NA-ACCORD site,3d1acd19-7cec-477a-bf93-297a04607ce0\n58d42927-16cd-459a-a3a3-5ad8d3eef981,070.70,2012-09-24,21,Data collected at NA-ACCORD site,8b063b82-3b36-4275-8ca6-cc8c125823fb\nacea2095-bb14-43c8-b009-b4fcb4f7f284,070.70,2017-05-21,1,Data collected at NA-ACCORD site,1c495c19-ff74-4cc0-b498-56b0d7c7985b\n"
        # risk factor
        # "data_content": "cohortPatientId,risk\n7ba7f43b-1467-4fe9-885d-26e775495651,Heterosexual contact - Sex with person with hemophilia\n4d52438d-02ff-48a0-be6d-e937ebe85351,Other\nd0f9d0ba-22d8-4a7a-b162-73a2c7f0627c,\"Receipt of blood transfusion, blood components, or tissue\"\nded0fb86-4b75-4b35-9412-5d13c9566cf0,Injection drug use\n5e28eaf0-7521-4006-a1d8-2d20a1a54e6b,\"Heterosexual contact - Sex with HIV-infected person, risk not specified\"\ncd1610f4-e773-491d-af9e-848c29ce3f03,Unknown\n1f9c4693-75e9-4e26-b98a-21167727ee6e,Worked in health care or laboratory setting\n778a43bb-2771-44dd-a69b-f9709a1f1092,Injection drug use\n808955fb-dcd9-45e6-9477-12c829c5ac4c,Hemophilia/coagulation disorder\ncbcec916-bbce-4770-8199-cb245a579f90,Heterosexual contact - Sex with bisexual male\n"
        # census
        # "data_content": "cohortPatientId,resDate,censusTract,zcta,county,state,mTractIncome,mZCTAIncome,mCountyIncome,mStateIncome,pTractEmployed,pZCTAEmployed,pCountyEmployed,pStateEmployed,pTractCollege,pZCTACollege,pCountyCollege,pStateCollege\n0dc5ca47-dc5c-4ca2-9d84-6b834d2c5cb9,1998-04-05,1896.54,14125,Perezmouth,South Dakota,37522,107941,135715,106370,0.45,0.79,0.69,0.39,0.31,0.83,0.74,0.94\ne4a73a7c-7514-4d23-80a7-13679f45c501,1995-11-13,9848.26,36641,Grayhaven,Massachusetts,105534,56825,140365,135074,0.24,0.65,0.42,0.86,0.32,0.49,0.65,0.12\n2f324c19-c116-4edb-a653-21ca44a9c68e,1999-06-10,5033.22,26003,North Brittanytown,Hawaii,133699,113700,105368,41815,0.9,0.48,0.6,0.87,0.17,0.54,0.16,0.26\ne333d0ab-c3cd-4356-9d6d-f5a637ca8a89,2012-10-29,9916.85,65740,Rileyside,Illinois,139235,29251,127479,91235,0.53,0.26,0.95,0.4,0.67,0.69,0.23,0.61\n0812a805-9402-4028-94e3-dfb415b5009e,2002-06-02,1443.37,51425,South Samuelberg,Washington,92823,122804,134281,133014,0.82,0.51,0.48,0.53,0.94,0.38,0.43,0.55\n2e34842e-6b96-4e5f-aaa1-d6a6fda67b7b,2018-01-31,9466.77,25903,New Maryshire,Virginia,113902,76006,35544,39044,0.84,0.49,0.0,0.76,0.28,0.29,0.38,0.48\n6d4dd58c-8cc3-4dd3-8e4f-fb9a2712aeaa,2024-06-29,2373.01,35105,North Leehaven,Washington,70004,28823,126759,82396,0.11,0.83,0.7,0.33,0.1,0.34,0.61,0.52\na9f1345a-98f8-44de-af5e-b4674b099561,2003-06-23,9513.93,64035,Wardville,Minnesota,49133,109403,32195,136134,0.99,0.0,0.64,0.13,0.81,0.18,0.16,0.4\n351051be-ee8b-44e8-b01e-8ffa75f71cd1,2001-07-15,8977.45,46861,Yangfurt,Wyoming,118647,139213,64312,83764,0.13,0.2,0.57,0.9,0.64,0.63,0.47,0.99\nfd4eec4b-9777-4940-9cd9-c321c730bc0d,2020-04-13,8110.77,36612,West Sean,New Hampshire,53923,140125,130013,141350,0.66,0.55,0.71,0.32,0.14,0.38,0.4,0.86\n",
    }

    # data_file_type = None
    # data_content = None

    def mount(self, request):
        user = request.user

        data_file_types = DataFileType.objects.all()

        self.data_file_type_options = transformed_data = [
            {"value": obj.name, "label": obj.label} for obj in data_file_types
        ]

    def post_handle(self, request):
        data_file_type = self.data["data_file_type"]
        upload_method = self.data["upload_method"]

        if upload_method == "upload":
            data_content = self.data["uploaded_csv_file"].read().decode("utf-8")
        else:
            data_content = self.data["data_content"]

        # Get the DataFileType object
        data_file_type_obj = DataFileType.objects.get(name=data_file_type)
        auditor = Auditor(data_file_type_obj, data_content)
        self.audit_report = auditor.handle()

        self.data["data_content"] = ""
        self.data["uploaded_csv_file"] = None

    # language=HTML
    template = """
        {% component "layout.app" title=title %}

            {% component "page_container" heading=title %}
            
            <div class="text-gray-600 text-sm">
            <p>Submit example data below to audit it. Auditing includes two steps:</p>
            <ul class="list-decimal list-inside mt-4 ml-4">
                <li>Validation: Checking the format of the data against the data table definition.</li>
                <li>Summarizing: Viewing a summary of the data to look for anomalies or other errors.</li>
            </ul>
            <p class="mt-4">Audited data will not be stored. The results of the audit will be shown below the form after submission.</p>
            </div>
            

            <div class="space-y-8">
                <form
                    class="mt-8 "
                    hx-post="{{ endpoint }}"
                    hx-swap-oob="true"
                    id="form"
                    enctype="multipart/form-data"
                    method="post"
                    x-data='{
                        uploadMethod: "{{ data.upload_method }}",
                        selectedFile: null,
                        error: false,
                        fileError: "",
                        processing: false,
                        selectFile() {
                            document.getElementById("fileInput").click();
                        },
                        handleFileSelect(event) {
                            const file = event.target.files[0];
                            if (file) {
                                const validExtensions = ["csv", "txt"];
                                const fileExtension = file.name.split(".").pop().toLowerCase();
                
                                if (!validExtensions.includes(fileExtension)) {
                                    alert("Invalid file type. Please upload a .csv or .txt file.");
                                    event.target.value = "";
                                    return;
                                }
                
                                this.selectedFile = file.name;
                            }
                        },
                        clearFile() {
                            document.getElementById("fileInput").value = "";
                            this.selectedFile = null;
                        }
                 
                    }'
                    @htmx:before-request.window="processing = true"
                    @htmx:after-request.window="processing = false"
                >
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-y-6">
                        
                        <div class="col-span-3">
                            {% component "input.radio"
                                name="data_file_type"
                                label="Data File Type"
                                options=data_file_type_options
                                data=data
                                errors=errors
                            /%}
                        </div>
                        
                        <div class='col-span-3'>
                            <input type="hidden" name="upload_method" x-bind:value="uploadMethod" />

                            {% component "input.radio" 
                                name="upload_method"
                                label="Upload Method"
                                errors=errors
                                xModel="uploadMethod"
                                options=upload_options
                                data=data
                            /%}

                        </div>
                        
                        <div class="col-span-3 relative" x-show="uploadMethod == 'upload'">
                                <input 
                                    type="file" 
                                    id="fileInput" 
                                    class="hidden" 
                                    name="uploaded_csv_file" 
                                    accept=".csv, .txt" 
                                    @change="handleFileSelect($event)"
                                />
                              <label for="upload" class="block text-sm/6 font-medium text-gray-900">File Select</label>
                              <div class="mt-3 flex items-center gap-x-6">
                                  {% component "icon" icon="file-csv" family="duotone" c="h-5 w-5 text-gray-600" /%}

                                                            
                                <template x-if="!selectedFile">
                                    <button 
                                        onclick="document.getElementById('fileInput').click()"
                                        type="button" 
                                        class="rounded-md bg-white px-2.5 py-1.5 text-xs-plus font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50
                                        @click="selectFile"
                                    ">Upload</button>
                                </template>
                                <template x-if="selectedFile">
                                    <div class="flex items-center space-x-2">
                                        <span class="text-sm text-gray-700" x-text="selectedFile"></span>
                                        <button 
                                            type="button" 
                                            class="text-red-600 hover:text-red-800 text-sm font-semibold" 
                                            @click="clearFile"
                                        >
                                            {% component "icon" icon="xmark" family="regular" c="h-3 w-3 fill-current" /%}
                                        </button>
                                    </div>
                                    
                                </template>
                                
                              </div>
                            
                               {% if errors.uploaded_csv_file %}  
                                <div class="mt-4 text-red-700 text-sm" hx-swap-oob="true">
                                    {{ errors.uploaded_csv_file.error_messages.0 }}
                                </div>
                                {% endif %}
                        </div>
                        
                        <div class="col-span-3" x-show="uploadMethod == 'paste'">
                            {% component "input.textarea" 
                                name="data_content"
                                label="Data Contents"
                                errors=errors 
                                attrs:rows=10
                                attrs:class="font-mono"
                                data=data
                                container_attrs:class="w-full" 
                            /%}
                            
                            {% if errors.data_content %}
                                <div class="mt-4 text-red-700 text-sm" hx-swap-oob="true">
                                    {{ errors.data_content.error_messages.0 }}
                                </div>
                            {% endif %}
                        </div>
                        
                        <div class="mt-4 col-span-3">
                        <button
                            type="{{ type }}"
                            class='w-36 flex justify-center rounded-md bg-red-600 px-3 py-1.5 text-sm font-semibold leading-6 text-white shadow-sm'
                            :class="processing ? ' opacity-50 cursor-not-allowed' : 'hover:bg-red-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600'"
                            :disabled="processing"
                        >
                            <span x-show="!processing">Audit</span>
                            <span class="flex items-center gap-x-2" x-show="processing">
                                {% component "loading" c="h-5 w-5" /%} Processing...
                            </span>
                        </button>

                        </div>
                 
                     
                    </div>
                </form>

                <div id="audit_report" hx-swap-oob="true">
                    {% if submitted %}
                        {% component "audit.report" report=audit_report /%}
                    {% endif %}
                </div> 
                
                
            </div>
            

            {% endcomponent %}

        {% endcomponent %}
    """
