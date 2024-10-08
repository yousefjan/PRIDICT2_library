import random
import pandas as pd
from Bio.Seq import Seq
from model_pred import pred
import os
from main import SF, fivep_homo, threep_homo, _get_control_rtt, _get_synony_rtt, _random_filler, get_preserving_rtt, _c, get_edit_position, trim_string, _make_df_freq
import matplotlib.pyplot as plt
import numpy as np

pd.set_option('future.no_silent_downcasting', True)

def rc(dna):
    complement = {'A': 'T', 'T': 'A', 'C': 'G', 'G': 'C', 'a': 't', 't': 'a', 'c': 'g', 'g': 'c'}
    return ''.join(complement[base] for base in reversed(dna))


def get_wt_rtt(seq, rtt): # pass rc of rtt for (+) PAM
    for i, base in enumerate(rtt):
        bases = ['A', 'T', 'G', 'C']
        if base.islower():
            bases.remove(base.upper())
            rtts = [(rtt[:i] + char + rtt[i+1:None]) for char in bases]
            for rtt in rtts:
                if rtt in seq:
                    return rtt

    return None


def generate_strings(seq, satArea):
    '''Returns list of all PRIDICT inputs for all bases in satArea
    '''
    allSeq = []
    startIndex = seq.index(satArea)
    endIndex = startIndex+len(satArea)
 
    for i in range(len(satArea)):
        bases = ['A','T','C','G']
        bases.remove(satArea[i])
        for j in range(len(bases)):
            editSeq = f'{seq[:startIndex]}{satArea[:i]}({satArea[i]}/{bases[j]}){satArea[i+1:]}{seq[endIndex:]}'
            allSeq.append(editSeq)
 
    # df = pd.DataFrame({'editseq': allSeq})
    # df['sequence_name'] = 'seq' + df.index.astype(str)
    # df.to_csv('./input/batch_template.csv')

    return allSeq
 

def get_reference(seq, rtt, wt_rtt, strand):
    """Returns reference sequence
    """
    if strand == '+':
        rtt = rc(rtt)

    start = seq.find(wt_rtt)

    diff = []
    diff.append(seq[:start])
    if len(rtt) == len(wt_rtt): # not 1bp del ctl
        for i in range(len(rtt)):
            if seq[start + i] != rtt[i]:
                diff.append(rtt[i].lower())
            else:
                diff.append(seq[start + i])

        diff.append(seq[start+len(rtt):])
        return ''.join(diff)
    else:
        del_idx = int(len(wt_rtt)/2)
        if strand == '+':
            return seq[:start+len(wt_rtt)-9-1] + '-' + seq[start+len(wt_rtt)-9:]
        else:
            return seq[:start+del_idx] + '-' + seq[start+del_idx+1:]


def run_pridict_lib(seq, sseq, frame, HA):
    """Returns PRIDICT2.0 based saturation library (with variable 3' extension structure)

    Sorted by PAM number (spacer)
    """

    def sort_result(unsorted_rs):
        # unsorted_rs = pd.read_csv('./npc_result.csv', index_col=False)
        pos_df = unsorted_rs[unsorted_rs['Strand']=='(+)'].reset_index(drop=True)
        neg_df = unsorted_rs[unsorted_rs['Strand']=='(-)'].reset_index(drop=True)

        pos_indx_lst = [seq.index(row['Spacer'][1:]) for _, row in pos_df.iterrows()]
        pos_df['Spacer Index'] = pos_indx_lst
        pos_df = pos_df.sort_values('Spacer Index', ignore_index=True)

        neg_indx_lst = [seq.index(rc(row['Spacer'][1:])) for _, row in neg_df.iterrows()]
        neg_df['Spacer Index'] = neg_indx_lst
        neg_df = neg_df.sort_values('Spacer Index', ascending=False, ignore_index=True)
        
        sorted_rs = pd.concat([pos_df, neg_df], ignore_index=True).reset_index(drop=True)

        PAMnum = 1
        old_indx = sorted_rs.iloc[0]['Spacer Index']
        for i, row in sorted_rs.iterrows():
            new_indx = row['Spacer Index']
            if old_indx!=new_indx:
                PAMnum+=1
            sorted_rs.at[i, 'PAM No.'] = PAMnum
            old_indx = new_indx
        
        # sorted_rs.insert(1, 'Spacer Index', sorted_rs.pop('Spacer Index'))
        sorted_rs.drop('Spacer Index', axis=1, inplace=True)

        sorted_rs['PAM No.'] = sorted_rs['PAM No.'].astype(int)
        sorted_rs.insert(1, 'PAM No.', sorted_rs.pop('PAM No.'))
        
        return sorted_rs
    
    pridict_input_sequences = generate_strings(seq, sseq)
    dfs = []
    for i, input in enumerate(pridict_input_sequences):
        pred(input)
        output = pd.read_csv('./predictions/seq_pegRNA_Pridict_full.csv')
        output = output[(output['RTrevcomp'].str.len() < 40) & (output['PBSrevcomp'].str.len() < 15) & (output['PBSrevcomp'].str.len() > 7)]
        max_scores = output.loc[output.groupby('Spacer-Sequence')['PRIDICT2_0_editing_Score_deep_HEK'].idxmax()]
        top_spacers = max_scores.sort_values(by='PRIDICT2_0_editing_Score_deep_HEK', ascending=False).head(4)
        for j in range(len(top_spacers.index)):
            df = pd.DataFrame()

            rtt = top_spacers.iloc[j]['RTrevcomp']
            strand = '(+)' if top_spacers.iloc[j]['Target-Strand'] == 'Fw' else '(-)'
            if strand[1] == '-':
                wt_rtt = get_wt_rtt(seq, rtt)
            else:
                wt_rtt = get_wt_rtt(seq, rc(rtt))
            

            df['peg No. (within edit)'] = [j+1]
            df['Edit Position (sat. area)'] = [i // 3 +1]
            df['PAM'] = [_c(top_spacers.iloc[j]['RTrevcomp'][-4]) + 'GG']
            df['Strand'] = [strand]
            df['Edit'] = [f'{top_spacers.iloc[j]['OriginalAllele']}>{top_spacers.iloc[j]['EditedAllele']}']
            df['LHA'] = [fivep_homo]
            df['Spacer'] = [top_spacers.iloc[j]['Spacer-Sequence']]
            df['Filler'] = 'GTTTCGAGACG' + _random_filler() + 'CGTCTCGGTGC'
            df['RTTs'] = [rtt]
            df['PBS'] = [top_spacers.iloc[j]['PBSrevcomp']]
            df['RHA'] = [threep_homo]
            if HA:
                df['Complete epegRNA'] = [fivep_homo + top_spacers.iloc[j]['Spacer-Sequence'] + df['Filler'].iloc[-1] + top_spacers.iloc[j]['RTrevcomp'] + top_spacers.iloc[j]['PBSrevcomp'] + threep_homo]
                df['Complete epegRNA (SF)'] = [fivep_homo + top_spacers.iloc[j]['pegRNA'] + threep_homo]  # Uses scaffold
            else:
                df['Complete epegRNA'] = [top_spacers.iloc[j]['Spacer-Sequence'] + df['Filler'].iloc[-1] + top_spacers.iloc[j]['RTrevcomp'] + top_spacers.iloc[j]['PBSrevcomp']]
                df['Complete epegRNA (SF)'] = [top_spacers.iloc[j]['pegRNA']]  # Uses scaffold

            df['Length (bp)'] = df['Complete epegRNA'].str.len()
            df['Length (bp) (SF)'] = df['Complete epegRNA (SF)'].str.len()
            df['Reference Sequence'] = [get_reference(seq, rtt, wt_rtt, strand[1])]
            df['PRIDICT2.0 Score'] = [top_spacers.iloc[j]['PRIDICT2_0_editing_Score_deep_HEK']]
            dfs.append(df)

    unsorted_lib = pd.concat(dfs, ignore_index=True)
    sorted_lib = sort_result(unsorted_lib)
    # sorted_lib = pd.read_csv('./saturation_library/npc_result.csv')

    # Get WT RTT for controls
    wt_rtts = []
    for _, group in sorted_lib.groupby('PAM No.'):
        ctl_row = group.loc[group['PRIDICT2.0 Score'].idxmax()].copy()
        if ctl_row['Strand']=='(-)':
            wt_rtt = get_wt_rtt(seq, ctl_row['RTTs'])
        else:
            wt_rtt= get_wt_rtt(seq, rc(ctl_row['RTTs']))

        wt_rtts.append(wt_rtt)

    # Getting control RTTs
    groups = []
    for i, group in sorted_lib.groupby('PAM No.'):
        new_row_stop = group.loc[group['PRIDICT2.0 Score'].idxmax()].copy()
        new_row_stop['RTTs'] = _get_control_rtt(seq, sseq, wt_rtts[i-1], frame, new_row_stop['Strand'][1], True, [])
        new_row_stop['Filler'] = 'GTTTCGAGACG' + _random_filler() + 'CGTCTCGGTGC'
        rtt = new_row_stop['RTTs']
        strand = new_row_stop['Strand'][1]
        new_row_stop['Reference Sequence'] = get_reference(seq, rtt, wt_rtt, strand)

        new_row_del = group.loc[group['PRIDICT2.0 Score'].idxmax()].copy()
        del_idx = int(len(wt_rtts[i-1])/2)
        new_row_del['RTTs'] = wt_rtts[i-1][:del_idx] + wt_rtts[i-1][del_idx+1:]
        new_row_del['Filler'] = 'GTTTCGAGACG' + _random_filler() + 'CGTCTCGGTGC'
        new_row_del['Reference Sequence'] = get_reference(seq, new_row_del['RTTs'], wt_rtt, new_row_stop['Strand'][1])

        groups.append(pd.concat([group, pd.DataFrame([new_row_stop, new_row_del])], ignore_index=True))

    df = pd.concat(groups, ignore_index=True)

    df_only_ctl = df.groupby('PAM No.').tail(2)
    df_no_ctl = df.drop(df_only_ctl.index)

    return df, df_no_ctl, df_only_ctl


def run_pridict_library_synony(seq, sseq, frame, HA, splice):
    """Returns PRIDICT2.0 based saturation library (with variable 3' extension structure) containing 
    silent mutation installing RTTs

    Sorted by PAM number (spacer)
    """

    df = pd.read_csv('./saturation_library/lib/no_ctl.csv')

    # Get WT RTT for controls
    wt_rtts = []
    for _, group in df.groupby('PAM No.'):
        ctl_row = group.loc[group['PRIDICT2.0 Score'].idxmax()].copy()
        if ctl_row['Strand']=='(-)':
            wt_rtt = get_wt_rtt(seq, ctl_row['RTTs'])
        else:
            wt_rtt= get_wt_rtt(seq, rc(ctl_row['RTTs']))

        wt_rtts.append(wt_rtt)

    rows = []
    for _, row in df.iterrows():
        row_syn = row.copy()

        # WT RTT for _get_synony_rtt()
        if row['Strand']=='(-)':
            wt_rtt = get_wt_rtt(seq, row['RTTs'])
        else:
            wt_rtt = get_wt_rtt(seq, rc(row['RTTs']))

        synony = _get_synony_rtt(seq=seq, sseq=sseq, rtt=wt_rtt, frame=frame, strand=row['Strand'][1], splice=splice)
        row_syn['RTTs'] = get_preserving_rtt(synony, row['RTTs'].upper(), wt_rtt)

        row_syn['Complete epegRNA'] = [fivep_homo + row['Spacer'] + 'GTTTCGAGACG' + _random_filler() + 'CGTCTCGGTGC' + row['RTTs'] + row['PBS'] + threep_homo]
        row_syn['Complete epegRNA (SF)'] = [fivep_homo + row['Spacer'] + SF + row['RTTs'] + row['PBS'] + threep_homo]
        row_syn['Syn. Mutation Position'] = 25-get_edit_position(row_syn['RTTs'], row['RTTs'].upper())-3-1
        row_syn['Reference Sequence'] = get_reference(seq, row_syn['RTTs'].upper(), wt_rtt, row['Strand'][1])
        row_syn['Filler'] = 'GTTTCGAGACG' + _random_filler() + 'CGTCTCGGTGC'

        rows.append(row_syn)

    df = pd.DataFrame(rows)

    # Getting control RTTs
    groups = []
    for i, group in df.groupby('PAM No.'):
        new_row_stop = group.loc[group['PRIDICT2.0 Score'].idxmax()].copy()
        new_row_stop['RTTs'] = _get_control_rtt(seq, sseq, wt_rtts[i-1], frame, new_row_stop['Strand'][1], True, splice)
        new_row_stop['Filler'] = 'GTTTCGAGACG' + _random_filler() + 'CGTCTCGGTGC'
        new_row_stop['Reference Sequence'] = get_reference(seq, new_row_stop['RTTs'], seq, wt_rtt)

        new_row_del = group.loc[group['PRIDICT2.0 Score'].idxmax()].copy()
        del_idx = int(len(wt_rtts[i-1])/2)
        new_row_del['RTTs'] = wt_rtts[i-1][:del_idx] + wt_rtts[i-1][del_idx+1:]
        new_row_del['Filler'] = 'GTTTCGAGACG' + _random_filler() + 'CGTCTCGGTGC'
        new_row_del['Reference Sequence'] = get_reference(seq, new_row_del['RTTs'], seq, wt_rtt)

        group_ = pd.concat([group, pd.DataFrame([new_row_stop, new_row_del])], ignore_index=True)
        groups.append(group_)

    new_rows_df = pd.concat(groups, ignore_index=True)

    if HA:
        new_rows_df['Complete epegRNA'] = new_rows_df['LHA'] + new_rows_df['Spacer'] + new_rows_df['Filler'] + new_rows_df['RTTs'] + new_rows_df['PBS'] + new_rows_df['RHA']
        new_rows_df['Length (bp)'] = new_rows_df['Complete epegRNA'].apply(lambda x: len(x))
        new_rows_df['Complete epegRNA (SF)'] = new_rows_df['LHA'] + new_rows_df['Spacer'] + SF + new_rows_df['RTTs'] + new_rows_df['PBS'] + new_rows_df['RHA']
        new_rows_df['Length (bp) (SF)'] = new_rows_df['Complete epegRNA (SF)'].apply(lambda x: len(x))
    else:
        new_rows_df['Complete epegRNA'] = new_rows_df['Spacer'] + new_rows_df['Filler'] + new_rows_df['RTTs'] + new_rows_df['PBS']
        new_rows_df['Length (bp)'] = new_rows_df['Complete epegRNA'].apply(lambda x: len(x))
        new_rows_df['Complete epegRNA (SF)'] = new_rows_df['Spacer'] + SF + new_rows_df['RTTs'] + new_rows_df['PBS']
        new_rows_df['Length (bp) (SF)'] = new_rows_df['Complete epegRNA (SF)'].apply(lambda x: len(x))

    new_rows_df.to_csv('./saturation_library/lib/synony_full.csv', index=False)


def _make_df_freq_pridict(seq, lib):
    lib['RTTs'] = lib['RTTs'].apply(lambda x: get_wt_rtt(seq, x))
    rtts = lib['RTTs'].to_list()
    return _make_df_freq(seq, rtts)


def run_freq_table(seq: str, sseq: str, lib) -> pd.DataFrame:
    seq = seq.upper()
    sseq = sseq.upper()
    seq = trim_string(seq, sseq)

    df = _make_df_freq_pridict(seq, lib)
    start = seq.index(sseq)
    end = start + len(sseq) - 1
    df_ = df[start:end + 1]
    df_['Position'] = np.arange(len(df_)) + 1
    return df_


def run_freq_plot(seq: str, sseq: str, lib) -> None:
    seq = seq.upper()
    sseq = sseq.upper()
    seq = trim_string(seq, sseq)

    df = _make_df_freq_pridict(seq, lib)

    start = seq.index(sseq)
    end = start + len(sseq) - 1
    df_ = df[start:end + 1]
    df_['Position'] = np.arange(len(df_)) + 1

    fig, ax = plt.subplots()

    ax.bar(df_['Position'],
           [freq if freq != 0 else -1 for freq in df_['Frequency']])
    ax.set_xlabel('Position')
    ax.set_ylabel('Frequency')
    ax.set_title('Frequency Plot')
    ax.margins(x=0, y=0)
    ax.axhline(y=0, color='r', linestyle='-')

    fig.canvas.draw()
    y_labels = [item.get_text() for item in ax.get_yticklabels()]

    y_labels[0] = '0'
    y_labels[1] = ''
    ax.set_yticklabels(y_labels)

    num_minus_ones = len([freq for freq in df_['Frequency'] if freq == 0])
    minus_one_positions = [pos for freq, pos in
                           zip(df_['Frequency'], df_['Position']) if freq == 0]
    minus_one_text = f'Total 0 Count: {num_minus_ones}\nPositions: {", ".join(map(str, minus_one_positions))}'

    ax.text(1.02, 0.5, minus_one_text, transform=ax.transAxes,
            verticalalignment='center',
            bbox=dict(facecolor='lightgray', alpha=0.5))

    plt.savefig('./saturation_library/lib/freq_plot.pdf', bbox_inches='tight')


if __name__=='__main__':

    # Set parameters: 
    seq_ = 'TACAGCTGGGTCTGACCTCTGAGTCCAGGGTCAGGTGATTTTGCTTAGCCTCAAGTGCTCAGATTCTGCTGATATTTTGCAAGACCTGGACTCTCTTGACACCCAGGATTCTTTCCTCAGGGGACATGCTGCCTATAGTTCTGCAGTTAACATCCTCCTTGGCCATGGCACCAGGGTCGGAGCCACGTACTTCATGACCTACCACACCGTGCTGCAGACCTCTGCTGACTTTATTGACGCTCTGAAGAAAGCCCGACTTATAGCCAGTAATGTCACCGAAACCATGGGCATTAACGGCAGTGCCTACCGAGTATTTCCTTACAGGTAAAGCCTGCCCTTTTTCAATGGGGTTTACCCAGCAAAGGGCCTACACTGGGTGGGAGTGGGGAGGGTTCCCTTGGCAAGATGCTGATTTTCAGGTTGGGTTCTGGCCCCTGCTCCATT'
    sseq_ = 'ACCCAGGATTCTTTCCTCAGGGGACATGCTGCCTATAGTTCTGCAGTTAACATCCTCCTTGGCCATGGCACCAGGGTCGGAGCCACGTACTTCATGACCTACCACACCGTGCTGCAGACCTCTGCTGACTTTATTGACGCTCTGAAGAAAGCCCGACTTATAGCCAGTAATGTCACCGAAACCATGGGCATTAACGGCAGTGCCTACCGAGTATTTCCTTACAGGTAAAGCCTGCCCTTTTTCA'
    acc = [18, 21]
    don = [223, 231]
    splice = list(range(acc[0] - 1, acc[1])) + list(range(don[0] - 1, don[1]))
    frame = +2
    homology = True # if you don't want, set to False

    libs = run_pridict_lib(seq_, sseq_, frame, HA=homology)

    libs[0].to_csv('./saturation_library/library/full.csv', index=False)
    libs[1].to_csv('./saturation_library/library/no_ctl.csv', index=False)
    libs[2].to_csv('./saturation_library/library/only_ctl.csv', index=False)

    run_pridict_library_synony(seq_, sseq_, frame, HA=homology, splice=splice)

    # Generates frequency table and plot
    lib = pd.read_csv('./saturation_library/library/no_ctl.csv')

    run_freq_plot(seq_, sseq_, lib.copy())
    run_freq_table(seq_, sseq_, lib).to_csv('./saturation_library/library/freq_table.csv', index=False)

    # -- Check results in 'lib' folder --

    print(get_wt_rtt(seq_, 'ACCTGGACTCTCTTGACtCCCAGGATTCTTTCCTC'))
