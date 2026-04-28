import pandas as pd
import os

df = pd.DataFrame({
    'Cliente': ['LUCIANA', 'JOISS'],
    'Telefone do contato': ['123', '456'],
    'Status do Atendimento': ['Aguardando Contato', 'Em Atendimento'],
    'Atendente': ['Chatbot', 'Chatbot'],
    'Fechado por': ['Chatbot', 'Chatbot'],
    'Tipo': ['receptivo', 'receptivo'],
    'Tempo primeira mensagem': ['00:10:00', '00:05:00']
})

writer = pd.ExcelWriter("test.xlsx", engine='xlsxwriter')
df.to_excel(writer, index=False, header=False, startrow=1, sheet_name='Relatorio_Chats')

workbook = writer.book
ws = writer.sheets['Relatorio_Chats']

(max_r, max_c) = df.shape
if max_r > 0:
    ws.add_table(0, 0, max_r, max_c - 1, {
        'columns': [{'header': str(c)} for c in df.columns],
        'style': 'Table Style Medium 9', 'name': 'Tab_Chats'
    })

writer.close()

# Now read it back
df2 = pd.read_excel("test.xlsx", engine='openpyxl')
print(df2.columns)
print(df2.head())
