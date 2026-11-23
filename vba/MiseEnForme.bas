Attribute VB_Name = "MiseEnForme"
' ============================================================================================
' Robo-advisor patrimonial - macro de mise en forme du fichier Excel du conseiller.
' Lancée automatiquement à l'ouverture (ThisWorkbook.Workbook_Open) ; relançable avec Alt+F8.
' Les onglets sont repérés par leur position (1 Synthèse, 2 Portefeuille, 3 Fil de décision,
' 4 Projection, 5 Conformité, 6 Réponses) pour fonctionner en français comme en anglais.
' ============================================================================================
Option Explicit

Private Const BLEU As Long = 4006164      ' RGB(20, 33, 61)  = #14213D
Private Const OR_ As Long = 5737904       ' RGB(176, 141, 87) = #B08D57
Private Const CLAIR As Long = 15462131    ' RGB(243, 238, 227)

Public Sub MiseEnForme()
    Dim ws As Worksheet
    Application.ScreenUpdating = False
    For Each ws In ThisWorkbook.Worksheets
        ws.Activate
        ActiveWindow.DisplayGridlines = False
        ws.Cells.Font.Name = "Calibri"
        ws.Rows(1).RowHeight = 28
        With ws.PageSetup
            .Orientation = xlLandscape
            .Zoom = False
            .FitToPagesWide = 1
            .FitToPagesTall = False
            .CenterFooter = "Projet pédagogique : outil d'aide à la décision simulé, pas un conseil en investissement"
            .RightFooter = "&P / &N"
        End With
    Next ws
    ColorerConformite ThisWorkbook.Worksheets(5)
    GraphiqueSynthese
    ThisWorkbook.Worksheets(1).Activate
    ThisWorkbook.Worksheets(1).Range("A1").Select
    Application.ScreenUpdating = True
End Sub

' Statut des contrôles : vert (ok), ambre (attention), rouge (bloquant)
Private Sub ColorerConformite(ws As Worksheet)
    Dim c As Range
    For Each c In ws.Range("B5:B" & ws.Cells(ws.Rows.Count, 1).End(xlUp).Row)
        Select Case LCase(c.Value)
            Case "ok": c.Interior.Color = RGB(230, 244, 234): c.Font.Color = RGB(30, 127, 79)
            Case "attention": c.Interior.Color = RGB(255, 244, 219): c.Font.Color = RGB(138, 90, 0)
            Case "bloquant": c.Interior.Color = RGB(253, 232, 232): c.Font.Color = RGB(179, 38, 30)
        End Select
        c.Font.Bold = True
        c.HorizontalAlignment = xlCenter
    Next c
End Sub

' Anneau d'allocation sur l'onglet Synthèse, à partir du tableau des classes de l'onglet Portefeuille
Private Sub GraphiqueSynthese()
    Dim wp As Worksheet, ws As Worksheet, debut As Long, fin As Long, co As ChartObject
    Set wp = ThisWorkbook.Worksheets(2)
    Set ws = ThisWorkbook.Worksheets(1)
    debut = wp.Cells(wp.Rows.Count, 1).End(xlUp).Row
    fin = debut
    Do While debut > 5 And wp.Cells(debut - 1, 2).Value <> "" And IsNumeric(wp.Cells(debut - 1, 2).Value)
        debut = debut - 1
    Loop
    For Each co In ws.ChartObjects
        co.Delete
    Next co
    Set co = ws.ChartObjects.Add(Left:=ws.Range("D4").Left, Top:=ws.Range("D4").Top, Width:=360, Height:=240)
    With co.Chart
        .ChartType = xlDoughnut
        .SetSourceData Source:=wp.Range(wp.Cells(debut, 1), wp.Cells(fin, 2))
        .HasTitle = True
        .ChartTitle.Text = "Allocation"
        .HasLegend = True
        .Legend.Position = xlLegendPositionRight
        .SeriesCollection(1).HasDataLabels = True
        .SeriesCollection(1).DataLabels.ShowPercentage = True
        .SeriesCollection(1).DataLabels.ShowValue = False
    End With
End Sub

' Exporte tout le classeur en PDF à côté du fichier (bouton ou Alt+F8)
Public Sub ExporterPDF()
    Dim chemin As String
    chemin = Replace(ThisWorkbook.FullName, ".xlsm", ".pdf")
    ThisWorkbook.ExportAsFixedFormat Type:=xlTypePDF, Filename:=chemin, Quality:=xlQualityStandard
    MsgBox "PDF enregistré : " & chemin, vbInformation
End Sub
