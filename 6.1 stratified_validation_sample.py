"""Reproducible, offline stratified validation sampling. No model/API calls.

Stages: frame, sample, install. Original production rows are the sampling units.
"""
from pathlib import Path
from collections import Counter
import argparse, csv, hashlib, json, math, random, re, shutil
import sys
from datetime import datetime
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.codex-task/stratified_validation_3000'
DEST = ROOT / 'data/10.人工验证/分层验证3000'
SEED = 20261107
FIELDS = ['case_time','province','city','district','specific_place','vehicle','death']
PROVINCES = dict(zip('京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼',
    ['北京市','天津市','上海市','重庆市','河北省','河南省','云南省','辽宁省','黑龙江省','湖南省','安徽省','山东省','新疆维吾尔自治区','江苏省','浙江省','江西省','湖北省','广西壮族自治区','甘肃省','山西省','内蒙古自治区','陕西省','吉林省','福建省','贵州省','广东省','青海省','西藏自治区','四川省','宁夏回族自治区','海南省']))
PROVINCES['内']='内蒙古自治区'
PROVINCES['黔']='贵州省'
FULL_NAMES = list(PROVINCES.values()) + ['香港特别行政区','澳门特别行政区','台湾省']
TARGETS = [ROOT / f'data/10.人工验证/{model}/manual_validation_sample_500.csv'
           for model in ['DeepSeek_V4_Pro','Gemini_3.5_Flash']]
csv.field_size_limit(100_000_000)

def raw_path(split):
    return ROOT / f'data/3.数据合并/裁判文书网2000-2021_{split}_4.csv'

def output_path(split):
    return ROOT / f'data/4.数据处理/transport_result_{split}_4.csv'

def save_json(path, obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

def frame():
    WORK.mkdir(parents=True,exist_ok=True)
    chunks=[]
    for split in range(1,5):
        cache=WORK/f'metadata_{split}.pkl'
        if cache.exists():
            d=pd.read_pickle(cache)
            print('Cached',split,len(d),flush=True)
        else:
            parts=[]; offset=0
            for d in pd.read_csv(raw_path(split),encoding='utf-8-sig',dtype=str,keep_default_na=False,
                                 usecols=['案号','法院','所属地区','案件类型','裁判日期'],chunksize=100000):
                d['source_split']=str(split)+'_4'
                d['source_row_id']=range(offset,offset+len(d))
                parts.append(d);offset+=len(d)
                print('Reading metadata',split,offset,flush=True)
            d=pd.concat(parts,ignore_index=True)
            d.to_pickle(cache)
        prod=pd.read_csv(output_path(split),dtype=str,keep_default_na=False,usecols=['row_id','案号','裁判日期'])
        assert len(d)==len(prod),(split,len(d),len(prod))
        assert prod['row_id'].astype(int).tolist()==list(range(len(d)))
        assert (prod['案号'].to_numpy()==d['案号'].to_numpy()).all()
        assert (prod['裁判日期'].to_numpy()==d['裁判日期'].to_numpy()).all()
        print('Production/source alignment verified',split,len(d),flush=True)
        chunks.append(d)
    d=pd.concat(chunks,ignore_index=True)
    assert len(d)==3298640,len(d)
    # Only standardized provincial court codes immediately after case year,
    # followed by a numeric court code, are used as direct provincial evidence.
    pat=r'^[（(]\d{4}[）)]\s*(['+''.join(PROVINCES)+r'])\d'
    codes=d['案号'].str.extract(pat,expand=False)
    d['stratum_province']=codes.map(PROVINCES).fillna('')
    d['province_basis']=d['stratum_province'].map(lambda x:'standard_case_number_code' if x else '')
    for col in ['法院','所属地区']:
        missing=d['stratum_province'].eq('')
        names=d.loc[missing,col].str.extract('('+'|'.join(FULL_NAMES)+')',expand=False)
        valid=names.dropna().index
        d.loc[valid,'stratum_province']=names.loc[valid]
        d.loc[valid,'province_basis']='explicit_province_in_'+col
    # Learn exact-name mappings solely from rows with direct metadata evidence.
    direct=d[d['stratum_province'].ne('')]
    for col in ['法院','所属地区']:
        pairs=direct[[col,'stratum_province']].drop_duplicates()
        pairs=pairs[pairs[col].ne('')]
        counts=pairs.groupby(col)['stratum_province'].nunique()
        pairs=pairs[pairs[col].isin(counts[counts.eq(1)].index)]
        mapping=pairs.set_index(col)['stratum_province']
        missing=d['stratum_province'].eq('')
        inferred=d.loc[missing,col].map(mapping).dropna()
        d.loc[inferred.index,'stratum_province']=inferred
        d.loc[inferred.index,'province_basis']='unambiguous_exact_'+col+'_mapping'
        pairs.to_csv(WORK/f'province_mapping_{col}.csv',index=False,encoding='utf-8-sig')
    d.loc[d['stratum_province'].eq(''),'stratum_province']='UNKNOWN_PROVINCE'
    d.loc[d['province_basis'].eq(''),'province_basis']='unresolved'
    rawyear=d['裁判日期'].str.extract(r'^\s*((?:19|20)\d{2})[-/年]',expand=False)
    caseyear=d['案号'].str.extract(r'^[（(]((?:19|20)\d{2})[）)]',expand=False)
    d['raw_judgment_year']=rawyear.fillna('')
    d['case_number_year']=caseyear.fillna('')
    d['stratum_year']=rawyear.fillna('UNKNOWN_YEAR')
    conflict=pd.to_numeric(caseyear,errors='coerce')>pd.to_numeric(rawyear,errors='coerce')
    d['year_quality_flag']='as_recorded'
    d.loc[rawyear.isna(),'year_quality_flag']='missing_or_unrecognized'
    d.loc[conflict,'year_quality_flag']='judgment_year_precedes_case_number_year'
    d.loc[conflict,'stratum_year']='UNKNOWN_YEAR'
    d['stratum_case_type']=d['案件类型'].map({'民事案件':'民事','刑事案件':'刑事'}).fillna('OTHER_OR_UNKNOWN')
    d['stratum_id']=d.stratum_year+'|'+d.stratum_province+'|'+d.stratum_case_type
    d.to_pickle(WORK/'frame.pkl')
    keys=['stratum_id','stratum_year','stratum_province','stratum_case_type']
    strata=d.groupby(keys,sort=True).size().reset_index(name='population_n')
    strata.to_csv(WORK/'frame_strata.csv',index=False,encoding='utf-8-sig')
    unknown=d[d['stratum_province'].eq('UNKNOWN_PROVINCE')]
    unknown.groupby(['法院','所属地区']).size().sort_values(ascending=False).to_csv(WORK/'unresolved_provinces.csv',encoding='utf-8-sig')
    report={'population_n':len(d),'nonempty_strata':len(strata),
            'minimum_sample_n':int(strata.population_n.clip(upper=2).sum()),
            'year_counts':d.stratum_year.value_counts().sort_index().to_dict(),
            'province_counts':d.stratum_province.value_counts().to_dict(),
            'case_type_counts':d.stratum_case_type.value_counts().to_dict(),
            'year_quality':d.year_quality_flag.value_counts().to_dict(),
            'province_basis':d.province_basis.value_counts().to_dict(),
            'source_alignment':'All 3,298,640 case numbers, judgment dates and zero-based row IDs verified against production outputs.'}
    save_json(WORK/'frame_summary.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

def sample():
    DEST.mkdir(parents=True,exist_ok=True)
    d=pd.read_pickle(WORK/'frame.pkl')
    s=pd.read_csv(WORK/'frame_strata.csv',dtype={'stratum_year':str})
    base=s.population_n.clip(upper=2)
    target=max(3000,int(base.sum()))
    remaining=target-int(base.sum())
    capacity=s.population_n-base
    numerators=capacity*remaining
    denominator=int(capacity.sum())
    extras=numerators//denominator if denominator else capacity*0
    leftover=remaining-int(extras.sum())
    # Exact largest-remainder allocation, with stable stratum-ID tie breaking.
    priority=sorted(s.index,key=lambda i:(-int(numerators.iloc[i]%denominator),s.stratum_id.iloc[i])) if denominator else []
    for i in priority[:leftover]:extras.iloc[i]+=1
    s['sample_n']=base+extras
    s['inclusion_probability']=s.sample_n/s.population_n
    s['sampling_weight']=s.population_n/s.sample_n
    assert int(s.sample_n.sum())==target
    assert s.sample_n.le(s.population_n).all()
    rng=random.Random(SEED)
    sizes=s.set_index('stratum_id').sample_n.to_dict()
    selected=[]
    for key, indices in d.groupby('stratum_id',sort=True).indices.items():
        selected.extend(rng.sample(indices.tolist(),int(sizes[key])))
    rng.shuffle(selected)
    chosen=d.loc[selected].copy().reset_index(drop=True)
    chosen['sample_id']=[f'SV20261107_{i:04d}' for i in range(1,target+1)]
    for col in ['population_n','sample_n','inclusion_probability','sampling_weight']:
        chosen[col]=chosen.stratum_id.map(s.set_index('stratum_id')[col])
    chosen.to_pickle(WORK/'selected.pkl')
    chosen.to_csv(DEST/'sample_index.csv',index=False,encoding='utf-8-sig')
    s.to_csv(DEST/'strata_allocation.csv',index=False,encoding='utf-8-sig')
    fetched={};predictions={}
    for split in range(1,5):
        sub=chosen[chosen.source_split.eq(f'{split}_4')]
        wanted=set(sub.source_row_id.astype(int)); offset=0
        for chunk in pd.read_csv(raw_path(split),dtype=str,keep_default_na=False,chunksize=20000):
            ids=wanted.intersection(range(offset,offset+len(chunk)))
            for rowid in sorted(ids):
                fetched[(f'{split}_4',rowid)]=chunk.iloc[rowid-offset].to_dict()
            offset+=len(chunk)
            if offset%200000==0:print('Fetching full texts',split,offset,flush=True)
            if offset>max(wanted,default=-1):break
        prod=pd.read_csv(output_path(split),dtype=str,keep_default_na=False)
        for row in prod[prod.row_id.astype(int).isin(wanted)].to_dict('records'):
            predictions[(f'{split}_4',int(row['row_id']))]=row
        print('Full texts fetched',split,len(sub),flush=True)
    assert len(fetched)==len(chosen)==len(predictions)
    try:
        oldtext=TARGETS[0].read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:
        oldtext=TARGETS[0].read_text(encoding='gb18030')
    oldfields=next(csv.reader(oldtext.splitlines()))
    # Retain all existing annotation columns; add source provenance and weights.
    extra=['source_split','source_file','original_output_file','stratum_id','stratum_year',
           'stratum_province','stratum_case_type','province_basis','raw_judgment_year',
           'case_number_year','year_quality_flag','population_n','sample_n',
           'inclusion_probability','sampling_weight','sampling_seed']
    columns=oldfields+[c for c in extra if c not in oldfields]
    rows=[];predrows=[]
    for meta in chosen.to_dict('records'):
        key=(meta['source_split'],int(meta['source_row_id']))
        source=fetched[key];pred=predictions[key]
        assert source['案号']==pred['案号']==meta['案号']
        assert source['裁判日期']==pred['裁判日期']==meta['裁判日期']
        row={c:'' for c in columns};row.update(source)
        row.update({c:meta[c] for c in meta if c in columns})
        split=int(meta['source_split'][0])
        row['source_file']=str(raw_path(split).relative_to(ROOT))
        row['original_output_file']=str(output_path(split).relative_to(ROOT))
        row['sampling_seed']=SEED
        rows.append(row)
        predrows.append({'sample_id':meta['sample_id'],'source_split':key[0],
                        'source_row_id':key[1],'案号':source['案号'],
                        **{'original_gemini_'+f:pred[f] for f in FIELDS}})
    assert len({(r['source_split'],r['source_row_id']) for r in rows})==target
    texts=Counter(hashlib.sha256(r['全文'].encode('utf-8')).hexdigest() for r in rows)
    doc_duplicates=sum(n-1 for n in texts.values() if n>1)
    assert doc_duplicates==0,('Duplicate full texts in selected sample',doc_duplicates)
    for filename, records, fields in [
        ('stratified_validation_sample_3000.csv',rows,columns),
        ('original_gemini_predictions_3000.csv',predrows,list(predrows[0]))]:
        with (DEST/filename).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(records)
    # Coverage tables include explicit unresolved categories rather than omitting them.
    for col in ['stratum_year','stratum_province','stratum_case_type']:
        coverage=pd.concat([d[col].value_counts().rename('population_n'),chosen[col].value_counts().rename('sample_n')],axis=1).fillna(0).sort_index()
        coverage.to_csv(DEST/f'coverage_{col}.csv',encoding='utf-8-sig')
    report={'seed':SEED,'population_n':len(d),'sample_n':target,'nonempty_strata':len(s),
            'covered_strata':chosen.stratum_id.nunique(),'duplicate_full_texts':doc_duplicates,
            'unique_case_numbers':chosen['案号'].nunique(),
            'sample_year_counts':chosen.stratum_year.value_counts().sort_index().to_dict(),
            'sample_province_counts':chosen.stratum_province.value_counts().to_dict(),
            'sample_case_type_counts':chosen.stratum_case_type.value_counts().to_dict(),
            'sample_year_quality':chosen.year_quality_flag.value_counts().to_dict(),
            'sampling_unit':'Production document row identified by source_split and zero-based source_row_id.',
            'allocation':'min(2,N_h) per nonempty stratum; remainder allocated proportionally to N_h-min(2,N_h), integer largest remainder; SRSWOR within strata.',
            'annotation_status':'All gold and human annotation fields intentionally blank; no model/API requests made.'}
    save_json(DEST/'sampling_manifest.json',report)
    (DEST/'抽样说明.txt').write_text(
        '本批样本用于重新开展人工验证，尚未完成标注。\n'
        f'总体为四个原始分片与原Gemini输出逐行对应的3,298,640条记录。样本数{target}，随机种子{SEED}。\n'
        '抽样单位为原始文书记录，不以最终筛选结果或LLM字段是否缺失限制入样。\n'
        '分层：原始裁判年份 × 法院省级地区 × 原始案件类型。其他案类、未知省份、未知年份独立保留。\n'
        '每个非空层先分配min(2,N_h)，剩余名额按剩余总体规模用最大余数法分配；层内无放回随机抽样。\n'
        '省份来自标准化案号省级代码、法院/所属地区中的明确省名，或由前两者建立的无歧义法院/地区精确名称映射；不使用LLM事故省份。无法确定时保留UNKNOWN_PROVINCE。\n'
        '裁判年份早于案号年份的记录归入UNKNOWN_YEAR，保留原始年份及冲突标记，需人工核查；不将案号年份当作裁判年份。\n'
        'source_row_id为各分片内从0开始的数据行编号，不含表头；必须与source_split联合使用。\n'
        '总体性能使用sampling_weight=N_h/n_h；字段性能的分子与有效分母均应用权重。每层2条只保证覆盖，不足以精确估计每个联合层的性能。\n'
        '原模型预测单独存放在original_gemini_predictions_3000.csv，人工标注时宜隐藏该文件。\n'
        '原500条文件名为兼容已有脚本而保留，覆盖后实际为本批新样本；新sample_id以SV20261107_开头。旧验证结果仍是旧500条，不能视为本批已完成结果。\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

def install():
    source=DEST/'stratified_validation_sample_3000.csv'
    manifest=json.loads((DEST/'sampling_manifest.json').read_text(encoding='utf-8'))
    with source.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    assert len(rows)==manifest['sample_n']
    assert all(not r['gold_case_time'] and not r['adjudicated'] for r in rows)
    backup=ROOT/'data/10.人工验证/备份'/('覆盖前500条_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=False)
    scripts=[t.parent/'run_deepseek_v4_pro_validation.py' for t in TARGETS]
    scripts.append(TARGETS[1].parent/'run_gemini_3_5_flash_validation.py')
    originals={}
    for p in TARGETS+scripts:
        dest=backup/p.parent.name/p.name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,dest);originals[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    for target in TARGETS:
        temp=target.with_suffix('.csv.tmp');shutil.copyfile(source,temp);temp.replace(target)
    # Keep legacy outputs intact. New runs write to separate result/status files.
    for p in scripts:
        txt=p.read_text(encoding='utf-8')
        txt=txt.replace('500-case validation sample','current stratified validation sample')
        txt=txt.replace('"VALIDATOR_FILE_STEM", "deepseek_v4_pro"','"VALIDATOR_FILE_STEM", "deepseek_v4_pro_stratified_3000"')
        txt=txt.replace('"VALIDATOR_FILE_STEM", "gemini_3_5_flash"','"VALIDATOR_FILE_STEM", "gemini_3_5_flash_stratified_3000"')
        if 'csv.field_size_limit(' not in txt and 'import csv' in txt:
            txt=txt.replace('BASE_DIR = Path(__file__).resolve().parent',
                'csv.field_size_limit(100_000_000)  # Preserve long source judgments.\n\nBASE_DIR = Path(__file__).resolve().parent')
        p.write_text(txt,encoding='utf-8')
        compile(txt,str(p),'exec')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    for target in TARGETS:
        assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
        with target.open(encoding='utf-8-sig',newline='') as f:
            checked=list(csv.DictReader(f))
        assert len(checked)==manifest['sample_n']
        assert len({r['sample_id'] for r in checked})==len(checked)
    result={'backup_directory':str(backup),'overwritten_files':[str(t) for t in TARGETS],
            'sample_n':len(rows),'new_sample_sha256':digest,'original_sha256':originals,
            'updated_scripts':[str(p) for p in scripts],'old_model_outputs':'preserved; new default filenames use _stratified_3000 suffix'}
    save_json(DEST/'installation_receipt.json',result)
    manifest['python_version']=sys.version
    manifest['pandas_version']=pd.__version__
    manifest['source_files']=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,
                              'mtime_ns':p.stat().st_mtime_ns}
                             for split in range(1,5) for p in [raw_path(split),output_path(split)]]
    manifest['sampling_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['sample_sha256']=digest
    save_json(DEST/'sampling_manifest.json',manifest)
    for supporting in ['frame_summary.json','province_mapping_法院.csv','province_mapping_所属地区.csv','unresolved_provinces.csv']:
        shutil.copy2(WORK/supporting,DEST/supporting)
    note=DEST/'抽样说明.txt'
    text=note.read_text(encoding='utf-8')
    reminder='注意：stratum_province为法院地区，仅用于分层，并非事故发生省份，不可直接填入gold_province。人工标注须依据事故事实原文。\n'
    if reminder not in text:note.write_text(text+reminder,encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['frame','sample','install'])
    args=parser.parse_args();globals()[args.stage]()
